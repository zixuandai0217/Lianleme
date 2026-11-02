"""规则评估纯函数测试（工单 41）。

用法与切分相同的合成关键点序列，直接断言规则评估的对外输出：
问题类型与严重度、0–10 评分、视角差异、高亮一致性、提示克制，
以及「规则路径零模型调用」。

这里不断言具体角度公式，只构造清晰的命中/未命中场景与阈值边界。
"""

import math

import pytest

from app.services.ai.pose_graph import PoseGraph
from app.services.pose.evaluation import (
    HINT_TEMPLATES,
    ISSUE_ASYMMETRY,
    ISSUE_KNEE_VALGUS,
    ISSUE_SHALLOW_DEPTH,
    ISSUE_TEMPO_OFF,
    ISSUE_TRUNK_LEAN,
    JOINT_LEFT_ANKLE,
    JOINT_LEFT_HIP,
    JOINT_LEFT_KNEE,
    JOINT_RIGHT_HIP,
    JOINT_RIGHT_KNEE,
    SEVERITY_ERROR,
    SEVERITY_WARN,
    Issue,
    evaluate_cycle,
    score_for_issues,
)
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

VISIBILITY = 0.95
# 髋（y=0.40）到膝（y=0.625）再到踝（y=0.85）的竖直腿链。
_LEG_HALF_HEIGHT = 0.225


# --- 合成关键点帧 -----------------------------------------------------------


def _blank_keypoints() -> list[dict]:
    return [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": VISIBILITY} for _ in range(33)]


def _knee_offset(angle_deg: float) -> float:
    """竖直髋-踝链下，膝角为 angle_deg 时膝相对竖直线的水平偏移。"""
    cosine = math.cos(math.radians(angle_deg))
    return _LEG_HALF_HEIGHT * math.sqrt((1.0 + cosine) / (1.0 - cosine))


def _front_frame(
    t_ms: int,
    *,
    left_angle: float = 178.0,
    right_angle: float = 178.0,
    left_inward: float | None = None,
    right_inward: float | None = None,
) -> dict:
    """正面帧：髋/踝在同一条竖直线上，膝横向偏移即膝内扣量。"""
    keypoints = _blank_keypoints()
    left_inward = _knee_offset(left_angle) if left_inward is None else left_inward
    right_inward = _knee_offset(right_angle) if right_inward is None else right_inward
    keypoints[INDEX_LEFT_SHOULDER] = {"x": 0.4, "y": 0.2, "z": 0.0, "visibility": VISIBILITY}
    keypoints[INDEX_RIGHT_SHOULDER] = {"x": 0.6, "y": 0.2, "z": 0.0, "visibility": VISIBILITY}
    for hip_index, knee_index, ankle_index, hip_x, inward in (
        (INDEX_LEFT_HIP, INDEX_LEFT_KNEE, INDEX_LEFT_ANKLE, 0.4, left_inward),
        (INDEX_RIGHT_HIP, INDEX_RIGHT_KNEE, INDEX_RIGHT_ANKLE, 0.6, -right_inward),
    ):
        keypoints[hip_index] = {"x": hip_x, "y": 0.40, "z": 0.0, "visibility": VISIBILITY}
        keypoints[knee_index] = {
            "x": hip_x + inward,
            "y": 0.625,
            "z": 0.0,
            "visibility": VISIBILITY,
        }
        keypoints[ankle_index] = {"x": hip_x, "y": 0.85, "z": 0.0, "visibility": VISIBILITY}
    return {"t_ms": t_ms, "keypoints": keypoints, "person_count": 1}


def _side_frame(
    t_ms: int,
    *,
    knee_angle: float = 100.0,
    trunk_lean_deg: float = 0.0,
) -> dict:
    """侧面帧：膝角由髋-膝-踝几何决定，躯干前倾角由肩相对髋的水平偏移决定。"""
    keypoints = _blank_keypoints()
    lean_dx = 0.2 * math.tan(math.radians(trunk_lean_deg))
    offset = _knee_offset(knee_angle)
    for shoulder_index, hip_index, knee_index, ankle_index, hip_x in (
        (INDEX_LEFT_SHOULDER, INDEX_LEFT_HIP, INDEX_LEFT_KNEE, INDEX_LEFT_ANKLE, 0.45),
        (INDEX_RIGHT_SHOULDER, INDEX_RIGHT_HIP, INDEX_RIGHT_KNEE, INDEX_RIGHT_ANKLE, 0.55),
    ):
        keypoints[shoulder_index] = {
            "x": hip_x + lean_dx,
            "y": 0.20,
            "z": 0.0,
            "visibility": VISIBILITY,
        }
        keypoints[hip_index] = {"x": hip_x, "y": 0.40, "z": 0.0, "visibility": VISIBILITY}
        keypoints[knee_index] = {
            "x": hip_x + offset,
            "y": 0.625,
            "z": 0.0,
            "visibility": VISIBILITY,
        }
        keypoints[ankle_index] = {"x": hip_x, "y": 0.85, "z": 0.0, "visibility": VISIBILITY}
    return {"t_ms": t_ms, "keypoints": keypoints, "person_count": 1}


def _sequence(times: list[int], factory, **frame_kwargs) -> list[dict]:
    return [factory(t_ms, **frame_kwargs) for t_ms in times]


def _clean_front_frames() -> list[dict]:
    """正面：膝不内扣、左右对称、节奏正常。"""
    times = [0, 500, 1000, 1500, 2000, 2600]
    angles = [178.0, 176.0, 173.0, 176.0, 173.0, 178.0]
    return [
        _front_frame(t_ms, left_angle=angle, right_angle=angle)
        for t_ms, angle in zip(times, angles)
    ]


def _clean_side_frames() -> list[dict]:
    """侧面：躯干直立、下蹲够深、节奏正常。"""
    times = [0, 500, 1000, 1500, 2000, 2600]
    angles = [178.0, 150.0, 100.0, 120.0, 150.0, 178.0]
    return [
        _side_frame(t_ms, knee_angle=angle, trunk_lean_deg=0.0)
        for t_ms, angle in zip(times, angles)
    ]


def _issue_types(evaluation) -> set[str]:
    return {issue.type for issue in evaluation.issues}


def _issue_of(evaluation, issue_type: str) -> Issue:
    for issue in evaluation.issues:
        if issue.type == issue_type:
            return issue
    raise AssertionError(f"未找到问题项 {issue_type}: {evaluation.issues}")


# --- 干净序列 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "camera_view"),
    [(_clean_front_frames, "front"), (_clean_side_frames, "side")],
)
def test_clean_sequence_scores_ten_without_issues(factory, camera_view):
    """没有规则命中时满分、无高亮、无提示，规则路径仍然有确定输出。"""
    evaluation = evaluate_cycle(factory(), camera_view=camera_view)

    assert evaluation.score == 10.0
    assert evaluation.issues == ()
    assert evaluation.highlights == ()
    assert evaluation.hint is None


# --- 膝内扣 -----------------------------------------------------------------


def test_knee_valgus_clear_hit_is_error_with_low_score():
    """明显膝内扣：类型、严重度、涉及关节与低分段评分都命中。"""
    frames = _sequence(
        [0, 1300, 2600],
        _front_frame,
        left_inward=0.082,
        right_inward=0.082,
    )
    # 让相邻帧的膝角有可测变化，避免把节奏问题混进来。
    frames[1]["keypoints"][INDEX_LEFT_KNEE]["x"] += 0.008
    frames[1]["keypoints"][INDEX_RIGHT_KNEE]["x"] -= 0.008

    evaluation = evaluate_cycle(frames, camera_view="front")
    issue = _issue_of(evaluation, ISSUE_KNEE_VALGUS)

    assert issue.severity == SEVERITY_ERROR
    assert JOINT_LEFT_KNEE in issue.joints
    assert JOINT_LEFT_HIP in issue.joints
    assert evaluation.score == 5.0
    assert 0.0 <= evaluation.score <= 10.0


def test_knee_valgus_clear_miss_has_no_issue():
    """膝在髋-踝线上：不产生膝内扣问题。"""
    evaluation = evaluate_cycle(_clean_front_frames(), camera_view="front")

    assert ISSUE_KNEE_VALGUS not in _issue_types(evaluation)


@pytest.mark.parametrize(
    ("left_inward", "right_inward", "expected"),
    [
        (0.033, 0.033, False),  # 比例 0.165，低于 warn 阈值
        (0.040, 0.040, True),  # 比例 0.200，命中 warn
        (0.078, 0.078, True),  # 比例 0.390，仍是 warn
        (0.082, 0.082, True),  # 比例 0.410，升级为 error
    ],
)
def test_knee_valgus_threshold_boundaries(left_inward, right_inward, expected):
    """膝内扣在阈值上下切换；同样比例的左右两侧只报一个问题。"""
    frames = _sequence(
        [0, 1300, 2600],
        _front_frame,
        left_inward=left_inward,
        right_inward=right_inward,
    )
    evaluation = evaluate_cycle(frames, camera_view="front")

    assert (ISSUE_KNEE_VALGUS in _issue_types(evaluation)) is expected
    if expected:
        types = [issue.type for issue in evaluation.issues]
        assert types.count(ISSUE_KNEE_VALGUS) == 1


def test_knee_valgus_error_boundary():
    """比例 0.390 为 warn，0.410 为 error。"""
    warning = evaluate_cycle(
        _sequence([0, 1300, 2600], _front_frame, left_inward=0.078, right_inward=0.078),
        camera_view="front",
    )
    error = evaluate_cycle(
        _sequence([0, 1300, 2600], _front_frame, left_inward=0.082, right_inward=0.082),
        camera_view="front",
    )

    assert _issue_of(warning, ISSUE_KNEE_VALGUS).severity == SEVERITY_WARN
    assert _issue_of(error, ISSUE_KNEE_VALGUS).severity == SEVERITY_ERROR


# --- 左右不对称 -------------------------------------------------------------


@pytest.mark.parametrize(
    ("right_angle", "expected"),
    [
        (170.0, False),  # 与左侧 160° 相差约 10°，低于 warn 阈值
        (174.0, True),  # 相差约 14°，命中 warn
    ],
)
def test_asymmetry_threshold_boundaries(right_angle, expected):
    frames = _sequence(
        [0, 1300, 2600],
        _front_frame,
        left_angle=160.0,
        right_angle=right_angle,
    )
    evaluation = evaluate_cycle(frames, camera_view="front")

    assert (ISSUE_ASYMMETRY in _issue_types(evaluation)) is expected
    if expected:
        issue = _issue_of(evaluation, ISSUE_ASYMMETRY)
        assert issue.severity == SEVERITY_WARN
        assert {JOINT_LEFT_KNEE, JOINT_RIGHT_KNEE} <= set(issue.joints)


# --- 躯干前倾 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("trunk_lean_deg", "expected_severity"),
    [
        (14.0, None),
        (16.0, SEVERITY_WARN),
        (31.0, SEVERITY_ERROR),
    ],
)
def test_trunk_lean_threshold_boundaries(trunk_lean_deg, expected_severity):
    frames = _sequence(
        [0, 1300, 2600],
        _side_frame,
        knee_angle=100.0,
        trunk_lean_deg=trunk_lean_deg,
    )
    evaluation = evaluate_cycle(frames, camera_view="side")

    if expected_severity is None:
        assert ISSUE_TRUNK_LEAN not in _issue_types(evaluation)
    else:
        issue = _issue_of(evaluation, ISSUE_TRUNK_LEAN)
        assert issue.severity == expected_severity
        assert JOINT_LEFT_HIP in issue.joints


# --- 下蹲深度 ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("knee_angle", "expected_severity"),
    [
        (119.0, None),
        (121.0, SEVERITY_WARN),
        (151.0, SEVERITY_ERROR),
    ],
)
def test_shallow_depth_threshold_boundaries(knee_angle, expected_severity):
    frames = _sequence(
        [0, 1300, 2600],
        _side_frame,
        knee_angle=knee_angle,
        trunk_lean_deg=0.0,
    )
    evaluation = evaluate_cycle(frames, camera_view="side")

    if expected_severity is None:
        assert ISSUE_SHALLOW_DEPTH not in _issue_types(evaluation)
    else:
        issue = _issue_of(evaluation, ISSUE_SHALLOW_DEPTH)
        assert issue.severity == expected_severity
        assert {JOINT_LEFT_KNEE, JOINT_LEFT_ANKLE} <= set(issue.joints)


# --- 节奏 -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("last_t_ms", "expected"),
    [
        (1799, True),
        (1800, False),
        (4500, False),
        (4501, True),
    ],
)
def test_tempo_duration_band_boundaries(last_t_ms, expected):
    frames = [
        _front_frame(0, left_angle=178.0, right_angle=178.0),
        _front_frame(last_t_ms // 2, left_angle=176.0, right_angle=176.0),
        _front_frame(last_t_ms, left_angle=178.0, right_angle=178.0),
    ]
    evaluation = evaluate_cycle(frames, camera_view="front")

    assert (ISSUE_TEMPO_OFF in _issue_types(evaluation)) is expected
    if expected:
        assert _issue_of(evaluation, ISSUE_TEMPO_OFF).severity == SEVERITY_WARN


def test_tempo_pause_ratio_boundary():
    """停顿占比超过一半才提示节奏问题。"""
    boundary = _sequence(
        [0, 500, 1000, 1500, 2000],
        _front_frame,
        left_angle=178.0,
        right_angle=178.0,
    )
    boundary[3] = _front_frame(1500, left_angle=175.0, right_angle=175.0)
    overdue = _sequence(
        [0, 400, 800, 1200, 1600, 2000],
        _front_frame,
        left_angle=178.0,
        right_angle=178.0,
    )
    overdue[4] = _front_frame(1600, left_angle=175.0, right_angle=175.0)

    assert ISSUE_TEMPO_OFF not in _issue_types(
        evaluate_cycle(boundary, camera_view="front")
    )
    assert ISSUE_TEMPO_OFF in _issue_types(
        evaluate_cycle(overdue, camera_view="front")
    )


# --- 视角 -------------------------------------------------------------------


def test_camera_view_selects_different_rule_sets():
    """同一段序列在正面与侧面得到不同的问题集合。"""
    frames = _sequence(
        [0, 1300, 2600],
        _front_frame,
        left_inward=0.078,
        right_inward=0.078,
    )
    frames[1]["keypoints"][INDEX_LEFT_KNEE]["x"] += 0.008
    frames[1]["keypoints"][INDEX_RIGHT_KNEE]["x"] -= 0.008

    front = evaluate_cycle(frames, camera_view="front")
    side = evaluate_cycle(frames, camera_view="side")

    assert ISSUE_KNEE_VALGUS in _issue_types(front)
    assert ISSUE_KNEE_VALGUS not in _issue_types(side)
    assert ISSUE_SHALLOW_DEPTH in _issue_types(side)
    assert _issue_types(front) != _issue_types(side)


# --- 高亮 -------------------------------------------------------------------


def test_highlights_are_derived_from_issues():
    """每个问题项对应一个高亮，颜色由 severity 区分，连线落在问题上。"""
    frames = _sequence(
        [0, 1300, 2600],
        _front_frame,
        left_inward=0.078,
        right_inward=0.078,
    )
    frames[1]["keypoints"][INDEX_LEFT_KNEE]["x"] += 0.008
    frames[1]["keypoints"][INDEX_RIGHT_KNEE]["x"] -= 0.008
    evaluation = evaluate_cycle(frames, camera_view="front")

    assert evaluation.highlights, "有问题项就必须有高亮"
    by_type = {highlight.issue_type: highlight for highlight in evaluation.highlights}
    assert set(by_type) == {issue.type for issue in evaluation.issues}
    for issue in evaluation.issues:
        highlight = by_type[issue.type]
        assert highlight.severity == issue.severity
        assert set(issue.joints) <= set(highlight.joints)

    valgus = by_type[ISSUE_KNEE_VALGUS]
    assert valgus.severity == SEVERITY_ERROR
    assert (JOINT_LEFT_HIP, JOINT_LEFT_KNEE) in valgus.segments
    assert (JOINT_LEFT_KNEE, JOINT_LEFT_ANKLE) in valgus.segments
    assert (JOINT_RIGHT_HIP, JOINT_RIGHT_KNEE) in valgus.segments


def test_no_issue_means_no_highlights():
    evaluation = evaluate_cycle(_clean_front_frames(), camera_view="front")

    assert evaluation.issues == ()
    assert evaluation.highlights == ()


# --- 提示 -------------------------------------------------------------------


def test_hint_reports_most_severe_issue_first_and_stays_restrained():
    """一句主提示 + 至多一句补充；先讲最严重的问题，不罗列全部。"""
    frames = _sequence(
        [0, 850, 1700],
        _front_frame,
        left_inward=0.082,
        right_inward=0.030,
    )
    evaluation = evaluate_cycle(frames, camera_view="front")

    assert _issue_of(evaluation, ISSUE_KNEE_VALGUS).severity == SEVERITY_ERROR
    assert _issue_of(evaluation, ISSUE_TEMPO_OFF).severity == SEVERITY_WARN
    assert evaluation.hint is not None
    assert evaluation.hint.startswith(HINT_TEMPLATES[ISSUE_KNEE_VALGUS])
    assert evaluation.hint.count("。") <= 2
    assert HINT_TEMPLATES[ISSUE_TEMPO_OFF] not in evaluation.hint


# --- 评分单调性与范围 -------------------------------------------------------


def _issue(severity: str) -> Issue:
    return Issue(type="synthetic", severity=severity, joints=(), hint="")


def test_score_decreases_with_severity_and_is_clamped():
    """问题越多、越严重，分数单调不升，并始终落在 0–10。"""
    cases = [
        [],
        [_issue(SEVERITY_WARN)],
        [_issue(SEVERITY_WARN), _issue(SEVERITY_WARN)],
        [_issue(SEVERITY_ERROR)],
        [_issue(SEVERITY_ERROR), _issue(SEVERITY_WARN)],
        [_issue(SEVERITY_ERROR), _issue(SEVERITY_ERROR)],
        [_issue(SEVERITY_ERROR), _issue(SEVERITY_ERROR), _issue(SEVERITY_ERROR)],
        [_issue(SEVERITY_ERROR)] * 4,
    ]
    scores = [score_for_issues(case) for case in cases]

    assert scores[0] == 10.0
    assert all(0.0 <= score <= 10.0 for score in scores)
    assert all(earlier >= later for earlier, later in zip(scores, scores[1:]))
    assert scores[-1] == 0.0


def test_cycle_score_matches_issue_table():
    frames = _sequence(
        [0, 850, 1700],
        _front_frame,
        left_inward=0.082,
        right_inward=0.030,
    )
    evaluation = evaluate_cycle(frames, camera_view="front")

    assert evaluation.score == score_for_issues(evaluation.issues)


# --- 零模型调用 -------------------------------------------------------------


def test_rule_evaluation_makes_zero_model_calls():
    """规则评估是图节点的一部分，但绝不递增模型调用计数。"""
    graph = PoseGraph()

    evaluation = graph.evaluate_cycle(_clean_front_frames(), camera_view="front")

    assert evaluation.score == 10.0
    assert graph.model_calls == 0
