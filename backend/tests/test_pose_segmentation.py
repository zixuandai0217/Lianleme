"""姿态周期切分的纯函数测试：不经过 HTTP，直接断言切分结果。

合成序列用「站立（膝角 ≈175°）→ 下蹲（膝角 90° 附近）→ 站立」的关键点轨迹，
覆盖成周期 / 等待 / 时长边界 / 质量门槛 / 窗口上限。
"""

import math

from app.services.pose.segmentation import (
    KNEE_CHAIN,
    SegmentationConfig,
    segment_window,
)

START_ANGLE = 175.0
BOTTOM_ANGLE = 90.0


def _leg_points(angle: float, x_center: float) -> tuple[tuple, tuple, tuple]:
    """按膝角构造髋/膝/踝三点（180° = 完全伸直，角度越小屈膝越深）。"""
    delta = math.radians(180.0 - angle)
    hip = (x_center, 0.40)
    knee = (x_center, 0.55)
    ankle = (knee[0] + 0.15 * math.sin(delta), knee[1] + 0.15 * math.cos(delta))
    return hip, knee, ankle


def _frame(
    t_ms: int,
    angle: float,
    *,
    visibility: float = 0.95,
    person_count: int = 1,
    x_shift: float = 0.0,
    hidden_ankles: bool = False,
) -> dict:
    """构造一帧 33 点关键点数据；hidden_ankles 用 0 可见度模拟单帧遮挡。"""
    keypoints = [
        {"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.95} for _ in range(33)
    ]
    for indices, x_center in ((KNEE_CHAIN.left, 0.45), (KNEE_CHAIN.right, 0.55)):
        hip, knee, ankle = _leg_points(angle, x_center)
        for position, (index, point) in enumerate(zip(indices, (hip, knee, ankle))):
            point_visibility = visibility
            if hidden_ankles and position == 2:
                point_visibility = 0.0
            keypoints[index] = {
                "x": point[0] + x_shift,
                "y": point[1],
                "z": 0.0,
                "visibility": point_visibility,
            }
    return {
        "t_ms": t_ms,
        "keypoints": keypoints,
        "person_count": person_count,
    }


def _angle_at(t_ms: int, segments: list[tuple[int, float, float]]) -> float:
    """按分段线性轨迹求某一时刻的膝角。"""
    cursor = 0
    for duration, start, end in segments:
        if t_ms <= cursor + duration:
            if duration <= 0:
                return end
            ratio = (t_ms - cursor) / duration
            return start + (end - start) * ratio
        cursor += duration
    return segments[-1][2]


def _sequence(
    segments: list[tuple[int, float, float]],
    *,
    fps: int = 4,
    **frame_kwargs,
) -> list[dict]:
    """把分段轨迹按固定帧率采样成关键点帧序列。"""
    interval = max(1, round(1000 / fps))
    total = sum(duration for duration, _, _ in segments)
    return [
        _frame(t_ms, _angle_at(t_ms, segments), **frame_kwargs)
        for t_ms in range(0, total + 1, interval)
    ]


def _rep_segments(
    *,
    hold_ms: int = 600,
    rep_ms: int = 2000,
    tail_ms: int = 600,
) -> list[tuple[int, float, float]]:
    """一次标准往返：起始保持 → 下蹲 → 起身 → 尾部保持。"""
    down = rep_ms // 2
    up = rep_ms - down
    return [
        (hold_ms, START_ANGLE, START_ANGLE),
        (down, START_ANGLE, BOTTOM_ANGLE),
        (up, BOTTOM_ANGLE, START_ANGLE),
        (tail_ms, START_ANGLE, START_ANGLE),
    ]


def test_incomplete_cycle_keeps_waiting():
    """只推送到下蹲途中：不成周期，会话保持等待。"""
    segments = [(600, START_ANGLE, START_ANGLE), (1000, START_ANGLE, BOTTOM_ANGLE)]
    outcome = segment_window(_sequence(segments))

    assert outcome.cycles == ()
    assert outcome.cycle_state == "waiting"
    assert outcome.pending_frames, "未成周期的帧必须留在待续窗口里"


def test_complete_cycle_reports_bounded_duration():
    """完整往返产生一个周期，起止与时长落在声明边界内。"""
    frames = _sequence(_rep_segments())
    outcome = segment_window(frames)

    assert len(outcome.cycles) == 1
    assert outcome.cycle_state == "completed"
    cycle = outcome.cycles[0]
    assert cycle.start_ms == frames[0]["t_ms"]
    assert cycle.end_ms > cycle.start_ms
    assert 1500 <= cycle.duration_ms <= 6000
    assert cycle.cycle_id.startswith("cyc_")
    assert cycle.evaluable is True
    assert cycle.camera_hint is None


def test_cycle_too_short_is_not_a_cycle():
    """快于 1.5 秒的往返不构成周期。"""
    frames = _sequence(_rep_segments(rep_ms=600))
    outcome = segment_window(frames)

    assert outcome.cycles == ()


def test_cycle_too_long_is_not_a_cycle():
    """慢于 6 秒的往返不构成周期（中途停顿也不能拼出一个周期）。"""
    segments = [
        (600, START_ANGLE, START_ANGLE),
        (2000, START_ANGLE, BOTTOM_ANGLE),
        (5000, BOTTOM_ANGLE, BOTTOM_ANGLE),
        (2000, BOTTOM_ANGLE, START_ANGLE),
        (400, START_ANGLE, START_ANGLE),
    ]
    outcome = segment_window(_sequence(segments))

    assert outcome.cycles == ()


def test_low_visibility_cycle_is_not_evaluable():
    """低可见度周期不可评估：给机位提示，不产生分数。"""
    frames = _sequence(_rep_segments(), visibility=0.4)
    outcome = segment_window(frames)

    assert len(outcome.cycles) == 1
    cycle = outcome.cycles[0]
    assert cycle.evaluable is False
    assert "low_visibility" in cycle.quality.reasons
    assert cycle.camera_hint


def test_out_of_frame_cycle_is_not_evaluable():
    """人体出框的周期不可评估。"""
    frames = _sequence(_rep_segments(), x_shift=-0.60)
    outcome = segment_window(frames)

    assert len(outcome.cycles) == 1
    assert outcome.cycles[0].evaluable is False
    assert "out_of_frame" in outcome.cycles[0].quality.reasons


def test_multiple_persons_cycle_is_not_evaluable():
    """多人入镜的周期不可评估。"""
    frames = _sequence(_rep_segments(), person_count=2)
    outcome = segment_window(frames)

    assert len(outcome.cycles) == 1
    assert outcome.cycles[0].evaluable is False
    assert "multiple_persons" in outcome.cycles[0].quality.reasons


def test_single_frame_dropout_is_interpolated():
    """单帧踝点遮挡可用线性插值补齐，不影响成周期。"""
    frames = _sequence(_rep_segments())
    middle = len(frames) // 2
    frames[middle] = _frame(
        frames[middle]["t_ms"],
        BOTTOM_ANGLE,
        hidden_ankles=True,
    )
    outcome = segment_window(frames)

    assert len(outcome.cycles) == 1


def test_pending_window_is_bounded_for_out_of_bounds_signal():
    """超长未闭合信号不会让待续窗口无限增长。"""
    segments = [
        (600, START_ANGLE, START_ANGLE),
        (1000, START_ANGLE, BOTTOM_ANGLE),
        (15000, BOTTOM_ANGLE, BOTTOM_ANGLE),
    ]
    frames = _sequence(segments)
    config = SegmentationConfig()
    outcome = segment_window(frames, config)

    assert outcome.cycles == ()
    pending = outcome.pending_frames
    assert pending
    span = pending[-1]["t_ms"] - pending[0]["t_ms"]
    assert span <= config.window_limit_ms
