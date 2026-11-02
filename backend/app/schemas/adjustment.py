"""调整结论的对外形状（工单 08）。

读取不依赖任何页面：计划解释（20）、打卡反馈（28）与运营追溯都从这里拿到同一份事实。
"""
import datetime
from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查时引入，避免 schema 依赖 ORM
    from app.models.adjustment import PlanAdjustment

AdjustmentDirection = Literal["increase", "decrease", "keep"]


class AdjustmentOutcomeResponse(BaseModel):
    """一次已落地调整的结论。"""

    adjustment_id: str = Field(..., description="稳定标识，下游引用它而不是时间或序号")
    plan_id: Optional[int] = Field(default=None, description="被调整的计划标识")
    direction: AdjustmentDirection = Field(..., description="increase / decrease / keep")
    reason: str = Field(..., description="用户可读理由，含触发数值")
    completion_rate: float = Field(..., ge=0, le=1, description="触发时的完成率 0-1")
    difficulty_rating: Optional[float] = Field(default=None, description="触发时的难度自评")
    created_at: datetime.datetime = Field(..., description="调整发生时间（UTC）")

    @classmethod
    def from_record(cls, record: "PlanAdjustment") -> "AdjustmentOutcomeResponse":
        """把 ORM 记录投影成对外形状；字段改名集中在这一处。"""
        return cls(
            adjustment_id=record.id,
            plan_id=record.plan_id,
            direction=record.direction,  # type: ignore[arg-type]
            reason=record.reason,
            completion_rate=record.completion_rate,
            difficulty_rating=record.difficulty_rating,
            created_at=record.created_at,
        )


class AdjustmentLatestResponse(BaseModel):
    """最近一次调整结论；没有调整记录时 ``outcome`` 为 null（不是 404、也不是伪造的 keep）。"""

    outcome: Optional[AdjustmentOutcomeResponse] = None
