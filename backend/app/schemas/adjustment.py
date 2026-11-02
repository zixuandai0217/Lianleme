"""调整结论的对外形状（工单 08，工单 24 追加评估明细）。

读取不依赖任何页面：计划解释（20）、打卡反馈（28）与运营追溯都从这里拿到同一份事实。
工单 24 在同一个响应里追加五维明细、合并小结与声明幅度；旧记录这些字段为 null，
读取形状不变（不新增端点、不改既有字段）。
"""
import datetime
from typing import TYPE_CHECKING, List, Literal, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查时引入，避免 schema 依赖 ORM
    from app.models.adjustment import PlanAdjustment

AdjustmentDirection = Literal["increase", "decrease", "keep"]
AdjustmentSource = Literal["rule", "llm"]
AdjustmentCompleteness = Literal["full", "partial", "default"]


class AdjustmentDimension(BaseModel):
    """单维评估结果：五维共用同一形状（工单 24 AC1）。"""

    name: str = Field(
        ..., description="completion / fatigue / injury_risk / sleep / body_composition"
    )
    score: float = Field(..., ge=0, le=10, description="健康评分：10 最好、0 最差")
    reason: str = Field(..., description="评分依据（用户可读）")
    suggestion: str = Field(..., description="该维度的调整建议")
    source: AdjustmentSource = Field(..., description="rule / llm")
    degraded: bool = Field(..., description="该路是否降级运行（失败 / 缺数据 / 未评估）")
    data_completeness: AdjustmentCompleteness = Field(
        ..., description="full / partial / default（default 不计入合并平均）"
    )


class AdjustmentRedFlag(BaseModel):
    """风险信号：只决定是否中断，不参与平均分（ADR-0004）。"""

    code: str = Field(
        ..., description="injury_risk_high / frequent_large_adjustment / goal_conflict"
    )
    severity: str = Field(..., description="high / medium")
    evidence: str = Field(..., description="支撑证据（维度与数值）")


class AdjustmentMergedSummary(BaseModel):
    """本周状态小结：整体健康分 + 剔除清单 + 风险信号 + 顶层理由。"""

    overall_score: float = Field(..., ge=0, le=10, description="参与维度的等权平均")
    dimension_scores: dict[str, float] = Field(default_factory=dict, description="五维得分")
    red_flags: List[AdjustmentRedFlag] = Field(default_factory=list)
    top_reasons: List[str] = Field(
        default_factory=list, description="最多 3 条，供解释卡片直接展示"
    )
    degraded_dimensions: List[str] = Field(default_factory=list)
    excluded_dimensions: List[str] = Field(
        default_factory=list, description="缺省、未计入平均的维度"
    )
    completeness: AdjustmentCompleteness = Field(..., description="本次评估的数据完整度")


class AdjustmentOutcomeResponse(BaseModel):
    """一次已落地调整的结论。"""

    adjustment_id: str = Field(..., description="稳定标识，下游引用它而不是时间或序号")
    plan_id: Optional[int] = Field(default=None, description="被调整的计划标识")
    direction: AdjustmentDirection = Field(..., description="increase / decrease / keep")
    reason: str = Field(..., description="用户可读理由，含触发数值")
    completion_rate: float = Field(..., ge=0, le=1, description="触发时的完成率 0-1")
    difficulty_rating: Optional[float] = Field(default=None, description="触发时的难度自评")
    created_at: datetime.datetime = Field(..., description="调整发生时间（UTC）")
    # 工单 24 追加：旧记录没有评估明细，这里为 null（读取不报错）。
    overall_score: Optional[float] = Field(default=None, description="合并后的整体健康分")
    delta_percent: Optional[float] = Field(default=None, description="本次声明幅度（0 表示保持）")
    dimensions: Optional[List[AdjustmentDimension]] = Field(
        default=None, description="五维明细，固定顺序；旧记录为 null"
    )
    merged: Optional[AdjustmentMergedSummary] = Field(
        default=None, description="合并小结；旧记录为 null"
    )

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
            overall_score=record.overall_score,
            delta_percent=record.delta_percent,
            dimensions=cls._project_dimensions(record.dimensions),
            merged=cls._project_merged(record.merged),
        )

    @staticmethod
    def _project_dimensions(raw: object) -> Optional[List[AdjustmentDimension]]:
        """历史记录可能为空或形态损坏：投影失败按「无明细」降级，不让读取 500。"""
        if not isinstance(raw, list) or not raw:
            return None
        try:
            return [AdjustmentDimension.model_validate(entry) for entry in raw]
        except Exception:  # noqa: BLE001 - 展示降级优于读取失败
            return None

    @staticmethod
    def _project_merged(raw: object) -> Optional[AdjustmentMergedSummary]:
        if not isinstance(raw, dict) or not raw:
            return None
        try:
            return AdjustmentMergedSummary.model_validate(raw)
        except Exception:  # noqa: BLE001 - 展示降级优于读取失败
            return None


class AdjustmentLatestResponse(BaseModel):
    """最近一次调整结论；没有调整记录时 ``outcome`` 为 null（不是 404、也不是伪造的 keep）。"""

    outcome: Optional[AdjustmentOutcomeResponse] = None
