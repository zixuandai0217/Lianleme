"""姿态周期切分：纯函数，无 I/O、无第三方依赖。

输入是一批关键点帧（MediaPipe 33 点，``x/y/z/visibility``），输出是已完成的
Motion Cycle 与仍待继续的帧窗口。切分信号是主关节角度（默认膝角 = 髋-膝-踝），
一个周期 =「稳定起始姿态（≥300ms）→ 明显偏离 → 回到起点附近」，且时长落在
1.5–6 秒内。时长越界的往返一律不构成周期，只让会话继续等待——这是
「不成周期就不评估」的第一道成本闸门。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

Frame = Mapping[str, Any]

# MediaPipe Pose 关键点索引（ADR-0002：后端保留全部 33 点）
INDEX_LEFT_SHOULDER = 11
INDEX_RIGHT_SHOULDER = 12
INDEX_LEFT_ELBOW = 13
INDEX_RIGHT_ELBOW = 14
INDEX_LEFT_WRIST = 15
INDEX_RIGHT_WRIST = 16
INDEX_LEFT_HIP = 23
INDEX_RIGHT_HIP = 24
INDEX_LEFT_KNEE = 25
INDEX_RIGHT_KNEE = 26
INDEX_LEFT_ANKLE = 27
INDEX_RIGHT_ANKLE = 28

CYCLE_STATE_WAITING = "waiting"
CYCLE_STATE_COMPLETED = "completed"

# 不可评估原因：稳定的错误码形状，前端据此选机位提示，不做自由文本判断。
REASON_MULTIPLE_PERSONS = "multiple_persons"
REASON_NO_PERSON = "no_person"
REASON_OUT_OF_FRAME = "out_of_frame"
REASON_LOW_VISIBILITY = "low_visibility"

_CAMERA_HINTS = {
    REASON_MULTIPLE_PERSONS: "画面里只保留一个人：让其他人先出镜，再开始这一组",
    REASON_NO_PERSON: "没看到人：确认手机对着你，站进画面再开始",
    REASON_OUT_OF_FRAME: "站进画面，让髋、膝、踝都完整入镜后再做",
    REASON_LOW_VISIBILITY: "光线太暗或被遮挡：换个亮一点的位置，让全身入镜",
}

_REASON_PRIORITY = (
    REASON_MULTIPLE_PERSONS,
    REASON_NO_PERSON,
    REASON_OUT_OF_FRAME,
    REASON_LOW_VISIBILITY,
)


@dataclass(frozen=True)
class JointChain:
    """一条关节链：(上端, 关节, 下端) 的左右两侧关键点索引。"""

    name: str
    left: tuple[int, int, int]
    right: tuple[int, int, int]


KNEE_CHAIN = JointChain("knee", (INDEX_LEFT_HIP, INDEX_LEFT_KNEE, INDEX_LEFT_ANKLE),
                        (INDEX_RIGHT_HIP, INDEX_RIGHT_KNEE, INDEX_RIGHT_ANKLE))
ELBOW_CHAIN = JointChain("elbow", (INDEX_LEFT_SHOULDER, INDEX_LEFT_ELBOW, INDEX_LEFT_WRIST),
                         (INDEX_RIGHT_SHOULDER, INDEX_RIGHT_ELBOW, INDEX_RIGHT_WRIST))
HIP_CHAIN = JointChain("hip", (INDEX_LEFT_SHOULDER, INDEX_LEFT_HIP, INDEX_LEFT_KNEE),
                       (INDEX_RIGHT_SHOULDER, INDEX_RIGHT_HIP, INDEX_RIGHT_KNEE))
DEFAULT_CHAIN = KNEE_CHAIN


@dataclass(frozen=True)
class SegmentationConfig:
    """切分与质量门槛；阈值集中在这里，便于按真实拍摄数据迭代。"""

    chain: JointChain = DEFAULT_CHAIN
    camera_view: str = "front"  # front：双侧加权平均；side：取可见度更高的一侧
    min_cycle_ms: int = 1500
    max_cycle_ms: int = 6000
    start_stable_ms: int = 300
    start_tolerance_deg: float = 8.0
    return_tolerance_deg: float = 12.0
    min_excursion_deg: float = 25.0
    min_joint_visibility: float = 0.3
    frame_visible_visibility: float = 0.5
    min_visibility_ratio: float = 0.6
    max_out_of_frame_ratio: float = 0.4
    # 相邻有效样本的最大间隔：覆盖 3 fps 下单帧遮挡（缺口 2 个采样间隔）。
    max_interpolation_gap_ms: int = 700
    out_of_frame_margin: float = 0.02
    trim_margin_ms: int = 1000

    @property
    def window_limit_ms(self) -> int:
        """待续窗口的保留上限：任何合法周期都不可能比它更长。"""
        return self.max_cycle_ms + self.start_stable_ms + self.trim_margin_ms


DEFAULT_CONFIG = SegmentationConfig()


@dataclass(frozen=True)
class CycleQuality:
    """周期的关键点质量统计；reasons 非空即不可评估。"""

    visibility_ratio: float
    out_of_frame_ratio: float
    person_count: int
    reasons: tuple[str, ...] = ()

    @property
    def evaluable(self) -> bool:
        return not self.reasons


@dataclass(frozen=True)
class DetectedCycle:
    """一个已完成的 Motion Cycle：只有时间与质量统计，不含关键点。"""

    cycle_id: str
    start_ms: int
    end_ms: int
    duration_ms: int
    quality: CycleQuality
    camera_hint: str | None

    @property
    def evaluable(self) -> bool:
        return self.quality.evaluable


@dataclass(frozen=True)
class CycleWindow:
    """一个已完成周期的原始帧窗口，仅供评估节点消费。

    帧窗口**不进入会话存储**：调用方评估完立即丢弃；``repr=False`` 避免调试
    或日志把关键点坐标带出去（隐私硬约束）。
    """

    cycle: DetectedCycle
    frames: tuple[Frame, ...] = field(repr=False)


@dataclass(frozen=True)
class SegmentationOutcome:
    """一次切分的结果：新完成的周期 + 仍需继续的帧窗口。"""

    completed: tuple[CycleWindow, ...] = ()
    pending_frames: tuple[Frame, ...] = ()
    cycle_state: str = CYCLE_STATE_WAITING

    @property
    def cycles(self) -> tuple[DetectedCycle, ...]:
        """只关心时间与质量统计时的视图，不含关键点。"""
        return tuple(window.cycle for window in self.completed)


@dataclass(frozen=True)
class _Sample:
    """某一帧的角度信号；weight 为该帧关键点的平均可见度。"""

    t_ms: int
    angle: float
    weight: float


def camera_hint_for(reasons: Sequence[str]) -> str | None:
    """按不可评估原因选一条机位提示；可评估时没有提示。"""
    for reason in _REASON_PRIORITY:
        if reason in reasons:
            return _CAMERA_HINTS[reason]
    return None


def _raw_keypoint(frame: Frame, index: int) -> tuple[float, float, float] | None:
    """读取一个关键点（不按可见度过滤），越界或非法数值返回 None。"""
    keypoints = frame.get("keypoints") or ()
    if index < 0 or index >= len(keypoints):
        return None
    point = keypoints[index]
    try:
        x = float(point["x"])
        y = float(point["y"])
        visibility = float(point.get("visibility", 1.0))
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(visibility)):
        return None
    return x, y, visibility


def _visible_keypoint(frame: Frame, index: int, config: SegmentationConfig):
    """读取用于角度计算的关键点：低置信度点不参与角度计算。"""
    point = _raw_keypoint(frame, index)
    if point is None or point[2] < config.min_joint_visibility:
        return None
    return point


def _angle(a: tuple, b: tuple, c: tuple) -> float | None:
    """计算 b 处的夹角（度）；退化向量返回 None。"""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1 = math.hypot(v1[0], v1[1])
    n2 = math.hypot(v2[0], v2[1])
    if n1 <= 0.0 or n2 <= 0.0:
        return None
    cosine = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _side_signal(
    frame: Frame,
    indices: tuple[int, int, int],
    config: SegmentationConfig,
) -> tuple[float, float] | None:
    """单侧关节角与权重（三点平均可见度）。"""
    points = [_visible_keypoint(frame, index, config) for index in indices]
    if any(point is None for point in points):
        return None
    angle = _angle(points[0], points[1], points[2])
    if angle is None:
        return None
    weight = sum(point[2] for point in points) / len(points)
    return angle, weight


def _frame_signal(
    frame: Frame,
    config: SegmentationConfig,
) -> tuple[float, float] | None:
    """一帧的主关节角信号；两侧都不可用时返回 None。"""
    sides = [
        signal
        for signal in (
            _side_signal(frame, config.chain.left, config),
            _side_signal(frame, config.chain.right, config),
        )
        if signal is not None
    ]
    if not sides:
        return None
    if config.camera_view == "side":
        # 侧拍时远端关节常被遮挡：只信可见度更高的一侧，避免平均值被拉偏。
        return max(sides, key=lambda item: item[1])
    total_weight = sum(weight for _, weight in sides)
    if total_weight <= 0.0:
        return None
    angle = sum(value * weight for value, weight in sides) / total_weight
    return angle, total_weight / len(sides)


def _signal_samples(
    frames: Sequence[Frame],
    config: SegmentationConfig,
) -> list[_Sample | None]:
    samples: list[_Sample | None] = []
    for frame in frames:
        signal = _frame_signal(frame, config)
        t_ms = int(frame.get("t_ms", 0))
        if signal is None:
            samples.append(None)
        else:
            samples.append(_Sample(t_ms, round(signal[0], 3), round(signal[1], 3)))
    return samples


def _interpolate_gaps(
    frames: Sequence[Frame],
    samples: list[_Sample | None],
    config: SegmentationConfig,
) -> list[_Sample | None]:
    """关键点缺失用线性插值补齐；间隔过大或位于首尾的缺口保持为空。"""
    filled = list(samples)
    index = 0
    while index < len(filled):
        if filled[index] is not None:
            index += 1
            continue
        start = index
        while index < len(filled) and filled[index] is None:
            index += 1
        end = index
        if start == 0 or end >= len(filled):
            continue
        before = filled[start - 1]
        after = filled[end]
        if before is None or after is None:
            continue
        gap = after.t_ms - before.t_ms
        if gap <= 0 or gap > config.max_interpolation_gap_ms:
            continue
        for position in range(start, end):
            t_ms = int(frames[position].get("t_ms", 0))
            ratio = max(0.0, min(1.0, (t_ms - before.t_ms) / gap))
            filled[position] = _Sample(
                t_ms,
                before.angle + (after.angle - before.angle) * ratio,
                0.0,
            )
    return filled


def _stable_run_end(
    samples: Sequence[_Sample | None],
    start_index: int,
    config: SegmentationConfig,
) -> int | None:
    """起始姿态稳定 300ms 的最后一个样本索引；不稳定或数据不足返回 None。"""
    sample = samples[start_index]
    if sample is None:
        return None
    base_angle = sample.angle
    for index in range(start_index + 1, len(samples)):
        current = samples[index]
        if current is None:
            return None
        if abs(current.angle - base_angle) > config.start_tolerance_deg:
            return None
        if current.t_ms - sample.t_ms >= config.start_stable_ms:
            return index
    return None


def _cycle_from_start(
    samples: Sequence[_Sample | None],
    start_index: int,
    config: SegmentationConfig,
) -> tuple[int, int] | None:
    """从给定起点找第一次回到起点附近的帧；时长越界则这个起点不成立。"""
    sample = samples[start_index]
    if sample is None:
        return None
    stable_end = _stable_run_end(samples, start_index, config)
    if stable_end is None:
        return None
    base_angle = sample.angle
    excursion_index = None
    for index in range(stable_end + 1, len(samples)):
        current = samples[index]
        if current is None:
            return None
        if current.t_ms - sample.t_ms > config.max_cycle_ms:
            return None
        if abs(current.angle - base_angle) >= config.min_excursion_deg:
            excursion_index = index
            break
    if excursion_index is None:
        return None
    for index in range(excursion_index + 1, len(samples)):
        current = samples[index]
        if current is None:
            return None
        if abs(current.angle - base_angle) > config.return_tolerance_deg:
            continue
        elapsed = current.t_ms - sample.t_ms
        if config.min_cycle_ms <= elapsed <= config.max_cycle_ms:
            return start_index, index
        # 第一次回到起点就落在时长边界外：这次往返不构成周期，不向后延展终点。
        return None
    return None


def _find_cycle(
    samples: Sequence[_Sample | None],
    config: SegmentationConfig,
    start_from: int,
) -> tuple[int, int] | None:
    """在窗口内找最早闭合的周期；同一终点取最晚的起点，让起点贴近动作开始。"""
    matches: list[tuple[int, int]] = []
    for start_index in range(start_from, len(samples) - 1):
        match = _cycle_from_start(samples, start_index, config)
        if match is not None:
            matches.append(match)
    if not matches:
        return None
    earliest_end = min(end for _, end in matches)
    latest_start = max(start for start, end in matches if end == earliest_end)
    return latest_start, earliest_end


def _frame_visibility(frame: Frame, config: SegmentationConfig) -> float:
    """一帧关节链关键点的平均可见度。"""
    values = []
    for index in config.chain.left + config.chain.right:
        point = _raw_keypoint(frame, index)
        if point is not None:
            values.append(point[2])
    return sum(values) / len(values) if values else 0.0


def _is_out_of_frame(frame: Frame, config: SegmentationConfig) -> bool:
    """关节链关键点是否越出画面（归一化坐标之外的容差外）。"""
    low = -config.out_of_frame_margin
    high = 1.0 + config.out_of_frame_margin
    for index in config.chain.left + config.chain.right:
        point = _raw_keypoint(frame, index)
        if point is None:
            continue
        if point[0] < low or point[0] > high or point[1] < low or point[1] > high:
            return True
    return False


def _frame_person_count(frame: Frame) -> int:
    try:
        return int(frame.get("person_count", 1) or 0)
    except (TypeError, ValueError):
        return 1


def _quality(frames: Sequence[Frame], config: SegmentationConfig) -> CycleQuality:
    """统计周期内的关键点质量并给出不可评估原因。"""
    if not frames:
        return CycleQuality(0.0, 0.0, 1, (REASON_NO_PERSON,))
    visibility_ratio = sum(_frame_visibility(frame, config) for frame in frames) / len(frames)
    out_of_frame_count = sum(1 for frame in frames if _is_out_of_frame(frame, config))
    person_count = max(_frame_person_count(frame) for frame in frames)

    reasons: list[str] = []
    if person_count > 1:
        reasons.append(REASON_MULTIPLE_PERSONS)
    if person_count < 1:
        reasons.append(REASON_NO_PERSON)
    if visibility_ratio < config.min_visibility_ratio:
        reasons.append(REASON_LOW_VISIBILITY)
    if out_of_frame_count / len(frames) > config.max_out_of_frame_ratio:
        reasons.append(REASON_OUT_OF_FRAME)

    return CycleQuality(
        visibility_ratio=round(visibility_ratio, 3),
        out_of_frame_ratio=round(out_of_frame_count / len(frames), 3),
        person_count=person_count,
        reasons=tuple(reasons),
    )


def _build_cycle(
    frames: Sequence[Frame],
    start_index: int,
    end_index: int,
    config: SegmentationConfig,
) -> DetectedCycle:
    start_ms = int(frames[start_index].get("t_ms", 0))
    end_ms = int(frames[end_index].get("t_ms", 0))
    quality = _quality(frames[start_index:end_index + 1], config)
    return DetectedCycle(
        cycle_id=f"cyc_{start_ms:08d}",
        start_ms=start_ms,
        end_ms=end_ms,
        duration_ms=end_ms - start_ms,
        quality=quality,
        camera_hint=None if quality.evaluable else camera_hint_for(quality.reasons),
    )


def _trim_window(frames: Sequence[Frame], config: SegmentationConfig) -> list[Frame]:
    """只保留最近一个可能成周期的窗口，避免内存随上传无限增长。"""
    window = list(frames)
    if not window:
        return window
    last_t_ms = int(window[-1].get("t_ms", 0))
    cut = 0
    while cut < len(window) - 1:
        if last_t_ms - int(window[cut].get("t_ms", 0)) <= config.window_limit_ms:
            break
        cut += 1
    return window[cut:]


def segment_window(
    frames: Sequence[Frame],
    config: SegmentationConfig = DEFAULT_CONFIG,
) -> SegmentationOutcome:
    """对帧窗口做周期切分，返回新完成的周期与待续窗口。"""
    window = list(frames)
    if not window:
        return SegmentationOutcome()
    samples = _interpolate_gaps(window, _signal_samples(window, config), config)

    cycles: list[CycleWindow] = []
    cursor = 0
    while cursor < len(window) - 1:
        found = _find_cycle(samples, config, cursor)
        if found is None:
            break
        start_index, end_index = found
        cycles.append(
            CycleWindow(
                cycle=_build_cycle(window, start_index, end_index, config),
                frames=tuple(window[start_index:end_index + 1]),
            )
        )
        cursor = end_index + 1

    pending = _trim_window(window[cursor:], config)
    return SegmentationOutcome(
        completed=tuple(cycles),
        pending_frames=tuple(pending),
        cycle_state=CYCLE_STATE_COMPLETED if cycles else CYCLE_STATE_WAITING,
    )
