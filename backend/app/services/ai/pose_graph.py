"""PoseGraph：姿态纠错图（工单 40 接帧/切分 + 41 规则评估 + 42 模型增强）。

完整形态（见 ``.scratch/pose-correction/issue.md``）::

    ingest_frames → segment_cycle ──未成周期──▶ 等待（不产出任何结果）
                         │
                         └─成周期─▶ recognize_action → evaluate_quality → feedback

规则评估是纯几何、确定性、零模型；模型增强只在可评估周期完成后追加一次调用
（动作识别 + 口语化改写 + 综合分），失败时退回规则结果并标记降级。没有 Key 时
整条链路只走规则，``model_calls`` 保持在 0——这是「规则优先、无 Key 可用」的
可断言证据。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from app.schemas.pose import CAMERA_VIEWS, DEFAULT_CAMERA_VIEW
from app.services.pose import evaluation, llm_coach
from app.services.pose.llm_coach import CycleEnhancement, PoseLLMCoach, ThrottleState
from app.services.pose.segmentation import (
    DEFAULT_CONFIG,
    SegmentationConfig,
    SegmentationOutcome,
    segment_window,
)

Frame = dict[str, Any]


class PoseGraph:
    """姿态图执行体：接帧 + 切分 + 规则评估 + 模型增强，可注入替身。"""

    def __init__(
        self,
        config: SegmentationConfig | None = None,
        *,
        coach: PoseLLMCoach | None = None,
    ) -> None:
        self.config = config or DEFAULT_CONFIG
        # 没有教练（未注入模型依赖）时整条链路纯规则，model_calls 恒为 0。
        self.coach = coach
        self.model_calls = 0

    def ingest_frames(
        self,
        window: Sequence[Frame],
        new_frames: Sequence[Frame],
    ) -> list[Frame]:
        """把新到达的帧并入当前未成周期的窗口（最老帧在前）。"""
        return [*window, *new_frames]

    def segment_cycle(
        self,
        frames: Sequence[Frame],
        *,
        camera_view: str = DEFAULT_CAMERA_VIEW,
    ) -> SegmentationOutcome:
        """按视角切分配置做周期切分；不成周期时返回等待态。"""
        view = camera_view if camera_view in CAMERA_VIEWS else DEFAULT_CAMERA_VIEW
        config = replace(self.config, camera_view=view)
        return segment_window(frames, config)

    def evaluate_cycle(
        self,
        frames: Sequence[Frame],
        *,
        camera_view: str = DEFAULT_CAMERA_VIEW,
    ) -> evaluation.CycleEvaluation:
        """规则评估节点：纯几何、确定性、零模型调用；用完即弃帧窗口。"""
        return evaluation.evaluate_cycle(frames, camera_view=camera_view)

    async def enhance_cycle(
        self,
        frames: Sequence[Frame],
        rule_evaluation: evaluation.CycleEvaluation,
        *,
        camera_view: str = DEFAULT_CAMERA_VIEW,
        exercise_hint: str | None = None,
        state: ThrottleState | None = None,
        now_ms: int = 0,
    ) -> CycleEnhancement:
        """模型增强节点：每周期最多一次调用；失败/无 Key/超预算都退回规则结果。"""
        if self.coach is None:
            return llm_coach.rule_only_enhancement(
                rule_evaluation,
                action=llm_coach.action_from_hint(exercise_hint),
                state=state,
                now_ms=now_ms,
            )
        enhancement = await self.coach.enhance(
            frames=frames,
            evaluation=rule_evaluation,
            camera_view=camera_view,
            exercise_hint=exercise_hint,
            state=state if state is not None else ThrottleState(),
            now_ms=now_ms,
        )
        if enhancement.called:
            self.model_calls += 1
        return enhancement
