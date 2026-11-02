"""PoseGraph：姿态纠错图（工单 40 的最小实现）。

完整形态（见 ``.scratch/pose-correction/issue.md``）::

    ingest_frames → segment_cycle ──未成周期──▶ 等待（不产出任何结果）
                         │
                         └─成周期─▶ recognize_action → evaluate_quality → feedback

本工单只实现前两个节点：**不调用任何模型**，也不产生评分、问题项或反馈文案。
``model_calls`` 恒为 0，是「不成周期就不消耗模型调用」这条成本闸门的可断言证据；
工单 41/42 接入识别与评估节点后才会递增。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from app.schemas.pose import CAMERA_VIEWS, DEFAULT_CAMERA_VIEW
from app.services.pose.segmentation import (
    DEFAULT_CONFIG,
    SegmentationConfig,
    SegmentationOutcome,
    segment_window,
)

Frame = dict[str, Any]


class PoseGraph:
    """姿态图执行体：接帧 + 周期切分，供路由层通过依赖注入替换为可控替身。"""

    def __init__(self, config: SegmentationConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG
        # 工单 40 不调用任何模型；该计数留给工单 41/42 的识别/评估节点。
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
