"""姿态周期的纯几何规则评估（工单 41）。

规则优先、模型为零：输入是一个已完成周期的帧窗口（33 点关键点 + 可见度）与
``camera_view``，输出确定性的问题项、0–10 质量分、骨架高亮与一句克制的提示。
这里不做网络请求、不读配置、不调用任何模型——断网或没有 Key 时这条路径照常工作。

视角决定规则子集与阈值：正面看膝内扣、左右对称与节奏；侧面看躯干前倾、下蹲
深度与节奏。阈值集中在本模块常量里，便于按真实拍摄数据迭代。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.services.pose.segmentation import (
    INDEX_LEFT_ANKLE,
    INDEX_LEFT_HIP,
    INDEX_LEFT_KNEE,
    INDEX_LEFT_SHOULDER,
    INDEX_RIGHT_ANKLE,
    INDEX_RIGHT_HIP,
    INDEX_RIGHT_KNEE,
    INDEX_RIGHT_SHOULDER,
)

Frame = Mapping[str, Any]
Point = tuple[float, float]

# --- 视角与稳定性词表 -------------------------------------------------------

VIEW_FRONT = "front"
VIEW_SIDE = "side"
CAMERA_VIEWS = frozenset({VIEW_FRONT, VIEW_SIDE})
DEFAULT_CAMERA_VIEW = VIEW_FRONT

# --- 问题类型与严重度（跨端契约） -------------------------------------------

ISSUE_KNEE_VALGUS = "knee_valgus"
ISSUE_TRUNK_LEAN = "trunk_lean"
ISSUE_ASYMMETRY = "asymmetry"
ISSUE_SHALLOW_DEPTH = "shallow_depth"
ISSUE_TEMPO_OFF = "tempo_off"

SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"
SEVERITY_ERROR = "critical"
_SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_WARN: 1, SEVERITY_INFO: 2}

# --- 关节名（响应里的稳定标识，前端据此映射骨架点） -------------------------

JOINT_LEFT_SHOULDER = "left_shoulder"
JOINT_RIGHT_SHOULDER = "right_shoulder"
JOINT_LEFT_HIP = "left_hip"
JOINT_RIGHT_HIP = "right_hip"
JOINT_LEFT_KNEE = "left_knee"
JOINT_RIGHT_KNEE = "right_knee"
JOINT_LEFT_ANKLE = "left_ankle"
JOINT_RIGHT_ANKLE = "right_ankle"

_SIDE_KNEE_JOINTS = {
    "left": (JOINT_LEFT_HIP, JOINT_LEFT_KNEE, JOINT_LEFT_ANKLE),
    "right": (JOINT_RIGHT_HIP, JOINT_RIGHT_KNEE, JOINT_RIGHT_ANKLE),
}
_TRUNK_JOINTS = (
    JOINT_LEFT_SHOULDER,
    JOINT_LEFT_HIP,
    JOINT_RIGHT_SHOULDER,
    JOINT_RIGHT_HIP,
)
_CHAIN_SEGMENTS = (
    (JOINT_LEFT_HIP, JOINT_LEFT_KNEE),
    (JOINT_LEFT_KNEE, JOINT_LEFT_ANKLE),
    (JOINT_RIGHT_HIP, JOINT_RIGHT_KNEE),
    (JOINT_RIGHT_KNEE, JOINT_RIGHT_ANKLE),
)
_TRUNK_SEGMENTS = (
    (JOINT_LEFT_SHOULDER, JOINT_LEFT_HIP),
    (JOINT_RIGHT_SHOULDER, JOINT_RIGHT_HIP),
)
_CHAIN_ISSUES = frozenset({ISSUE_KNEE_VALGUS, ISSUE_ASYMMETRY, ISSUE_SHALLOW_DEPTH})

# --- 阈值（角度单位：度；横向偏移按髋宽归一化） -----------------------------

MIN_JOINT_VISIBILITY = 0.3
MIN_HIP_WIDTH = 0.02
MIN_TRUNK_HEIGHT = 0.05

# 膝内扣：膝越过髋-踝连线的横向偏移 / 髋宽。只在屈膝帧上判断，避免站直时的
# 自然外八被误判。
VALGUS_MAX_BEND_DEG = 170.0
VALGUS_WARN_RATIO = 0.18
VALGUS_ERROR_RATIO = 0.40

# 侧面躯干前倾：肩-髋连线与竖直方向的夹角。
TRUNK_LEAN_WARN_DEG = 15.0
TRUNK_LEAN_ERROR_DEG = 30.0

# 左右膝角差。
ASYMMETRY_WARN_DEG = 12.0
ASYMMETRY_ERROR_DEG = 25.0

# 下蹲深度：周期内最小膝角越大表示蹲得越浅。
SHALLOW_WARN_DEG = 120.0
SHALLOW_ERROR_DEG = 150.0

# 节奏：常用往返为 2–4 秒，留出慢速/大重量余量；停顿占比按相邻帧膝角变化统计。
TEMPO_MIN_MS = 1800
TEMPO_MAX_MS = 4500
PAUSE_DELTA_DEG = 2.0
PAUSE_RATIO_MAX = 0.5

# --- 评分与提示 -------------------------------------------------------------

MAX_SCORE = 10.0
MIN_SCORE = 0.0
SCORE_DECIMALS = 1
# 有严重问题直接压到低分段（10 - 5 = 5），提示级只轻扣。
SEVERITY_PENALTY = {SEVERITY_ERROR: 5.0, SEVERITY_WARN: 2.0, SEVERITY_INFO: 0.0}
HINT_SEPARATOR = " "

HINT_TEMPLATES = {
    ISSUE_KNEE_VALGUS: "膝盖往外推一点，朝脚尖方向打开。",
    ISSUE_TRUNK_LEAN: "上身别往前趴，胸口抬起来、核心收紧。",
    ISSUE_ASYMMETRY: "两边下沉的幅度不一样，慢一点、让左右一起走。",
    ISSUE_SHALLOW_DEPTH: "再蹲深一点，髋往下坐。",
    ISSUE_TEMPO_OFF: "节奏有点偏，下去慢一点、起来稳住。",
}


@dataclass(frozen=True)
class Issue:
    """一条规则命中的问题项；joints 用稳定关节名，前端据此高亮骨架。"""

    type: str
    severity: str
    joints: tuple[str, ...] = ()
    hint: str = ""


@dataclass(frozen=True)
class Highlight:
    """问题项对应的骨架高亮：severity 让 UI 决定红（error）或橙（warn）。"""

    joints: tuple[str, ...]
    segments: tuple[tuple[str, str], ...]
    severity: str
    issue_type: str


@dataclass(frozen=True)
class CycleEvaluation:
    """一个周期的规则评估结果；没有问题时 score 为 10、点列为空。"""

    score: float
    issues: tuple[Issue, ...] = ()
    highlights: tuple[Highlight, ...] = ()
    hint: str | None = None


@dataclass(frozen=True)
class _Measurements:
    """一次遍历窗口得到的规则输入；None 表示该维度没有足够可见的关键点。"""

    valgus_ratio: float | None = None
    valgus_sides: tuple[str, ...] = ()
    trunk_lean_deg: float | None = None
    asymmetry_deg: float | None = None
    min_knee_angle_deg: float | None = None
    duration_ms: int | None = None
    pause_ratio: float | None = None


# --- 几何工具 ---------------------------------------------------------------


def _point(frame: Frame, index: int) -> Point | None:
    """取一个可见的关键点；低置信度、越界或非法数值一律不参与计算。"""
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
    if visibility < MIN_JOINT_VISIBILITY:
        return None
    return x, y


def _angle(a: Point, b: Point, c: Point) -> float | None:
    """计算 b 处的夹角（度）；退化向量返回 None。"""
    first = (a[0] - b[0], a[1] - b[1])
    second = (c[0] - b[0], c[1] - b[1])
    norm_first = math.hypot(*first)
    norm_second = math.hypot(*second)
    if norm_first <= 0.0 or norm_second <= 0.0:
        return None
    cosine = (first[0] * second[0] + first[1] * second[1]) / (norm_first * norm_second)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _knee_angle(frame: Frame, side: str) -> float | None:
    """一侧的膝角（髋-膝-踝）；任一点不可见即返回 None。"""
    indices = (
        (INDEX_LEFT_HIP, INDEX_LEFT_KNEE, INDEX_LEFT_ANKLE)
        if side == "left"
        else (INDEX_RIGHT_HIP, INDEX_RIGHT_KNEE, INDEX_RIGHT_ANKLE)
    )
    hip, knee, ankle = (_point(frame, index) for index in indices)
    if hip is None or knee is None or ankle is None:
        return None
    return _angle(hip, knee, ankle)


def _line_x_at_y(hip: Point, ankle: Point, y: float) -> float | None:
    """髋-踝连线在给定 y 处的 x；连线水平或退化时返回 None。"""
    if abs(ankle[1] - hip[1]) <= 1e-6:
        return None
    ratio = (y - hip[1]) / (ankle[1] - hip[1])
    return hip[0] + (ankle[0] - hip[0]) * ratio


def _valgus_sides(frame: Frame) -> dict[str, float]:
    """一帧里左右膝的内扣比例（仅取正值，且只在屈膝帧上判断）。"""
    left_hip = _point(frame, INDEX_LEFT_HIP)
    right_hip = _point(frame, INDEX_RIGHT_HIP)
    left_ankle = _point(frame, INDEX_LEFT_ANKLE)
    right_ankle = _point(frame, INDEX_RIGHT_ANKLE)
    if None in (left_hip, right_hip, left_ankle, right_ankle):
        return {}
    hip_width = abs(right_hip[0] - left_hip[0])
    if hip_width < MIN_HIP_WIDTH:
        return {}
    # 左右关键点是主体视角的命名：内扣方向一律指向两髋中点。
    order = 1.0 if left_hip[0] <= right_hip[0] else -1.0
    entries = (
        ("left", left_hip, _point(frame, INDEX_LEFT_KNEE), left_ankle, order),
        ("right", right_hip, _point(frame, INDEX_RIGHT_KNEE), right_ankle, -order),
    )
    ratios: dict[str, float] = {}
    for side, hip, knee, ankle, sign in entries:
        if hip is None or knee is None or ankle is None:
            continue
        knee_angle = _angle(hip, knee, ankle)
        if knee_angle is None or knee_angle > VALGUS_MAX_BEND_DEG:
            continue
        line_x = _line_x_at_y(hip, ankle, knee[1])
        if line_x is None:
            continue
        ratio = sign * (knee[0] - line_x) / hip_width
        if ratio > 0.0:
            ratios[side] = ratio
    return ratios


def _trunk_lean(frame: Frame) -> float | None:
    """一帧里两侧躯干前倾角的最大值；肩必须明显高于髋。"""
    angles: list[float] = []
    for shoulder_index, hip_index in (
        (INDEX_LEFT_SHOULDER, INDEX_LEFT_HIP),
        (INDEX_RIGHT_SHOULDER, INDEX_RIGHT_HIP),
    ):
        shoulder = _point(frame, shoulder_index)
        hip = _point(frame, hip_index)
        if shoulder is None or hip is None:
            continue
        height = hip[1] - shoulder[1]
        if height <= MIN_TRUNK_HEIGHT:
            continue
        angles.append(math.degrees(math.atan2(abs(shoulder[0] - hip[0]), height)))
    return max(angles) if angles else None


def _frame_t_ms(frame: Frame) -> int | None:
    try:
        return int(frame.get("t_ms", 0))
    except (TypeError, ValueError):
        return None


def _measure(frames: Sequence[Frame]) -> _Measurements:
    """遍历窗口，汇总各规则需要的最差值。"""
    valgus_by_side: dict[str, float] = {}
    trunk_lean: float | None = None
    asymmetry: float | None = None
    min_knee: float | None = None
    knee_sequence: list[float | None] = []
    times: list[int | None] = []

    for frame in frames:
        times.append(_frame_t_ms(frame))

        for side, ratio in _valgus_sides(frame).items():
            valgus_by_side[side] = max(valgus_by_side.get(side, 0.0), ratio)

        lean = _trunk_lean(frame)
        if lean is not None:
            trunk_lean = lean if trunk_lean is None else max(trunk_lean, lean)

        left_angle = _knee_angle(frame, "left")
        right_angle = _knee_angle(frame, "right")
        for angle in (left_angle, right_angle):
            if angle is not None:
                min_knee = angle if min_knee is None else min(min_knee, angle)
        if left_angle is not None and right_angle is not None:
            gap = abs(left_angle - right_angle)
            asymmetry = gap if asymmetry is None else max(asymmetry, gap)
        valid_angles = [angle for angle in (left_angle, right_angle) if angle is not None]
        knee_sequence.append(sum(valid_angles) / len(valid_angles) if valid_angles else None)

    valid_times = [t_ms for t_ms in times if t_ms is not None]
    duration = valid_times[-1] - valid_times[0] if len(valid_times) >= 2 else None

    paused = 0
    transitions = 0
    for previous, current in zip(knee_sequence, knee_sequence[1:]):
        if previous is None or current is None:
            continue
        transitions += 1
        if abs(current - previous) < PAUSE_DELTA_DEG:
            paused += 1
    pause_ratio = paused / transitions if transitions else None

    affected: list[str] = []
    for side in ("left", "right"):
        if valgus_by_side.get(side, 0.0) >= VALGUS_WARN_RATIO:
            affected.append(side)

    return _Measurements(
        valgus_ratio=max(valgus_by_side.values()) if affected else None,
        valgus_sides=tuple(affected),
        trunk_lean_deg=trunk_lean,
        asymmetry_deg=asymmetry,
        min_knee_angle_deg=min_knee,
        duration_ms=duration,
        pause_ratio=pause_ratio,
    )


# --- 规则 -------------------------------------------------------------------


def _knee_valgus_issue(measurements: _Measurements) -> Issue | None:
    ratio = measurements.valgus_ratio
    if ratio is None:
        return None
    severity = SEVERITY_ERROR if ratio >= VALGUS_ERROR_RATIO else SEVERITY_WARN
    joints = tuple(
        joint for side in measurements.valgus_sides for joint in _SIDE_KNEE_JOINTS[side]
    )
    return Issue(
        type=ISSUE_KNEE_VALGUS,
        severity=severity,
        joints=joints,
        hint=HINT_TEMPLATES[ISSUE_KNEE_VALGUS],
    )


def _trunk_lean_issue(measurements: _Measurements) -> Issue | None:
    angle = measurements.trunk_lean_deg
    if angle is None or angle <= TRUNK_LEAN_WARN_DEG:
        return None
    severity = SEVERITY_ERROR if angle > TRUNK_LEAN_ERROR_DEG else SEVERITY_WARN
    return Issue(
        type=ISSUE_TRUNK_LEAN,
        severity=severity,
        joints=_TRUNK_JOINTS,
        hint=HINT_TEMPLATES[ISSUE_TRUNK_LEAN],
    )


def _asymmetry_issue(measurements: _Measurements) -> Issue | None:
    gap = measurements.asymmetry_deg
    if gap is None or gap <= ASYMMETRY_WARN_DEG:
        return None
    severity = SEVERITY_ERROR if gap > ASYMMETRY_ERROR_DEG else SEVERITY_WARN
    joints = _SIDE_KNEE_JOINTS["left"] + _SIDE_KNEE_JOINTS["right"]
    return Issue(
        type=ISSUE_ASYMMETRY,
        severity=severity,
        joints=joints,
        hint=HINT_TEMPLATES[ISSUE_ASYMMETRY],
    )


def _shallow_depth_issue(measurements: _Measurements) -> Issue | None:
    angle = measurements.min_knee_angle_deg
    if angle is None or angle <= SHALLOW_WARN_DEG:
        return None
    severity = SEVERITY_ERROR if angle > SHALLOW_ERROR_DEG else SEVERITY_WARN
    joints = _SIDE_KNEE_JOINTS["left"] + _SIDE_KNEE_JOINTS["right"]
    return Issue(
        type=ISSUE_SHALLOW_DEPTH,
        severity=severity,
        joints=joints,
        hint=HINT_TEMPLATES[ISSUE_SHALLOW_DEPTH],
    )


def _tempo_issue(measurements: _Measurements) -> Issue | None:
    duration = measurements.duration_ms
    too_fast = duration is not None and duration < TEMPO_MIN_MS
    too_slow = duration is not None and duration > TEMPO_MAX_MS
    too_much_pause = (
        measurements.pause_ratio is not None
        and measurements.pause_ratio > PAUSE_RATIO_MAX
    )
    if not (too_fast or too_slow or too_much_pause):
        return None
    return Issue(
        type=ISSUE_TEMPO_OFF,
        severity=SEVERITY_WARN,
        joints=(JOINT_LEFT_KNEE, JOINT_RIGHT_KNEE),
        hint=HINT_TEMPLATES[ISSUE_TEMPO_OFF],
    )


def _front_rules(measurements: _Measurements) -> tuple[Issue | None, ...]:
    return (
        _knee_valgus_issue(measurements),
        _asymmetry_issue(measurements),
        _tempo_issue(measurements),
    )


def _side_rules(measurements: _Measurements) -> tuple[Issue | None, ...]:
    return (
        _trunk_lean_issue(measurements),
        _shallow_depth_issue(measurements),
        _tempo_issue(measurements),
    )


# --- 评分、高亮与提示 -------------------------------------------------------


def score_for_issues(issues: Sequence[Issue]) -> float:
    """10 分起步，按严重度扣分；更多/更严重的问题只会让分数更低，并夹在 0–10。"""
    penalty = sum(SEVERITY_PENALTY.get(issue.severity, 0.0) for issue in issues)
    score = max(MIN_SCORE, min(MAX_SCORE, MAX_SCORE - penalty))
    return round(score, SCORE_DECIMALS)


def _segments_for(issue: Issue) -> tuple[tuple[str, str], ...]:
    if issue.type in _CHAIN_ISSUES:
        candidates = _CHAIN_SEGMENTS
    elif issue.type == ISSUE_TRUNK_LEAN:
        candidates = _TRUNK_SEGMENTS
    else:
        candidates = ()
    joints = set(issue.joints)
    return tuple(
        segment for segment in candidates if segment[0] in joints and segment[1] in joints
    )


def _highlight(issue: Issue) -> Highlight:
    return Highlight(
        joints=issue.joints,
        segments=_segments_for(issue),
        severity=issue.severity,
        issue_type=issue.type,
    )


def _compose_hint(issues: Sequence[Issue]) -> str | None:
    """一句主提示，至多一句补充；issues 已按严重度排序。"""
    if not issues:
        return None
    primary = issues[0].hint
    if len(issues) == 1:
        return primary
    return f"{primary}{HINT_SEPARATOR}{issues[1].hint}"


def evaluate_cycle(
    frames: Sequence[Frame],
    *,
    camera_view: str = DEFAULT_CAMERA_VIEW,
) -> CycleEvaluation:
    """评估一个已完成的周期窗口；纯函数、确定性、零模型调用。"""
    view = camera_view if camera_view in CAMERA_VIEWS else DEFAULT_CAMERA_VIEW
    measurements = _measure(frames)
    rule_results = _front_rules(measurements) if view == VIEW_FRONT else _side_rules(
        measurements
    )
    issues = tuple(
        sorted(
            (issue for issue in rule_results if issue is not None),
            key=lambda issue: _SEVERITY_ORDER.get(issue.severity, len(_SEVERITY_ORDER)),
        )
    )
    return CycleEvaluation(
        score=score_for_issues(issues),
        issues=issues,
        highlights=tuple(_highlight(issue) for issue in issues),
        hint=_compose_hint(issues),
    )
