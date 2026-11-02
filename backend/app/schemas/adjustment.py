"""调整结论的对外形状（工单 08，工单 24 追加评估明细）。

读取不依赖任何页面：计划解释（20）、打卡反馈（28）与运营追溯都从这里拿到同一份事实。
工单 24 在同一个响应里追加五维明细、合并小结与声明幅度；旧记录这些字段为 null，
读取形状不变（不新增端点、不改既有字段）。
"""
import datetime
from typing import TYPE_CHECKING, List, Literal, Optional

from pydantic import BaseModel, Field

from app.models.adjustment_job import (
    effective_error_code,
    effective_failure_class,
    effective_landed,
    effective_status,
)

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查时引入，避免 schema 依赖 ORM 实例
    from app.models.adjustment import PlanAdjustment
    from app.models.adjustment_job import PlanAdjustmentJob

AdjustmentDirection = Literal["increase", "decrease", "keep"]
AdjustmentSource = Literal["rule", "llm"]
AdjustmentCompleteness = Literal["full", "partial", "default"]
AdjustmentJobStatus = Literal[
    "evaluating", "pending_choice", "applied", "expired_no_choice", "failed"
]


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


class AdjustmentJobDecision(BaseModel):
    """本次调整的决策：方向、幅度与动作层面的落地形式。"""

    direction: AdjustmentDirection = Field(..., description="increase / decrease / keep")
    delta_percent: float = Field(..., description="声明幅度；keep 为 0")
    exercise_swaps: List[dict] = Field(
        default_factory=list,
        description="动作替换清单；工单 24 的 Graph 不产出时为不伪造的空数组",
    )
    rest_day_change: Optional[dict] = Field(
        default=None, description="休息日变更；工单 24 的 Graph 不产出时为 null"
    )


class AdjustmentPlanDiff(BaseModel):
    """评估时快照的计划前后差异；之后计划再变也不改写这次交代。"""

    before_difficulty_factor: float
    after_difficulty_factor: float
    before_summary: str
    after_summary: str
    changed_days: List[int] = Field(default_factory=list)


class AdjustmentJobSummary(BaseModel):
    """作业列表项：足以判断「评估中 / 已落地 / 失败」，详情按需拉取。"""

    job_id: str
    status: AdjustmentJobStatus
    created_at: datetime.datetime
    updated_at: datetime.datetime
    landed: bool = Field(..., description="是否已落地（applied / expired_no_choice）")
    landed_at: Optional[datetime.datetime] = None
    direction: Optional[AdjustmentDirection] = None
    failure_class: Optional[str] = None
    error_code: Optional[str] = None

    @classmethod
    def from_job(cls, job: "PlanAdjustmentJob") -> "AdjustmentJobSummary":
        return cls(
            job_id=job.job_id,
            status=effective_status(job),  # type: ignore[arg-type]
            created_at=job.created_at,
            updated_at=job.updated_at,
            landed=effective_landed(job),
            landed_at=job.landed_at,
            direction=_decision_direction(job.decision),
            failure_class=effective_failure_class(job),
            error_code=effective_error_code(job),
        )


class AdjustmentJobDetail(AdjustmentJobSummary):
    """作业详情：五维小结、合并分、决策、前后差异与失败分类。"""

    adjustment_id: Optional[str] = Field(
        default=None, description="已落地时对应的调整结论标识"
    )
    dimensions: Optional[List[AdjustmentDimension]] = Field(
        default=None, description="五维明细，固定顺序；未完成评估时为 null"
    )
    merged: Optional[AdjustmentMergedSummary] = Field(
        default=None, description="合并小结；未完成评估时为 null"
    )
    decision: Optional[AdjustmentJobDecision] = None
    plan_diff: Optional[AdjustmentPlanDiff] = None
    interrupt: Optional[dict] = Field(
        default=None, description="待用户选择时的 interrupt 载荷；工单 27 写入"
    )
    # 工单 27：决定者与所选项；非 interrupt 作业这两项为 null。
    chosen_by: Optional[str] = Field(
        default=None, description="user / timeout_default；尚未落地时为 null"
    )
    chosen_option: Optional[str] = Field(
        default=None, description="落地方案的稳定 id；尚未落地时为 null"
    )
    interrupt_expires_at: Optional[datetime.datetime] = Field(
        default=None, description="待选择窗口截止时间（UTC）；非 interrupt 作业为 null"
    )

    @classmethod
    def from_job(
        cls, job: "PlanAdjustmentJob", adjustment: Optional["PlanAdjustment"] = None
    ) -> "AdjustmentJobDetail":
        summary = AdjustmentJobSummary.from_job(job)
        return cls(
            **summary.model_dump(),
            adjustment_id=job.adjustment_id,
            dimensions=(
                AdjustmentOutcomeResponse._project_dimensions(adjustment.dimensions)
                if adjustment is not None
                else None
            ),
            merged=(
                AdjustmentOutcomeResponse._project_merged(adjustment.merged)
                if adjustment is not None
                else None
            ),
            decision=_project_decision(job.decision),
            plan_diff=_project_plan_diff(job.plan_diff),
            interrupt=_project_interrupt(job.interrupt),
            chosen_by=job.chosen_by,
            chosen_option=job.chosen_option,
            interrupt_expires_at=job.interrupt_expires_at,
        )


class AdjustmentResumeRequest(BaseModel):
    """用户拍板：只提交选项 id，选项集合来自 interrupt 载荷。"""

    option_id: str = Field(
        ..., min_length=1, max_length=64, description="interrupt 载荷里的 option id"
    )


class AdjustmentResumeResponse(AdjustmentJobDetail):
    """恢复结果：与详情同形，前端不需要第二套解析。"""


class AdjustmentJobPending(BaseModel):
    """未决作业：评估中或等待用户选择；``interrupt`` 供风险确认模态使用。"""

    job_id: str
    status: AdjustmentJobStatus
    created_at: datetime.datetime
    updated_at: datetime.datetime
    interrupt: Optional[dict] = None

    @classmethod
    def from_job(cls, job: "PlanAdjustmentJob") -> "AdjustmentJobPending":
        return cls(
            job_id=job.job_id,
            status=effective_status(job),  # type: ignore[arg-type]
            created_at=job.created_at,
            updated_at=job.updated_at,
            interrupt=_project_interrupt(job.interrupt),
        )


def _project_interrupt(raw: object) -> Optional[dict]:
    """对外 interrupt 载荷：去掉落地时用的内部评估快照，其余原样。"""
    if not isinstance(raw, dict) or not raw:
        return None
    return {key: value for key, value in raw.items() if key != "evaluation"}


def _decision_direction(raw: object) -> Optional[AdjustmentDirection]:
    if not isinstance(raw, dict):
        return None
    direction = raw.get("direction")
    if direction in ("increase", "decrease", "keep"):
        return direction  # type: ignore[return-value]
    return None


def _project_decision(raw: object) -> Optional[AdjustmentJobDecision]:
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return AdjustmentJobDecision.model_validate(raw)
    except Exception:  # noqa: BLE001 - 展示降级优于读取失败
        return None


def _project_plan_diff(raw: object) -> Optional[AdjustmentPlanDiff]:
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return AdjustmentPlanDiff.model_validate(raw)
    except Exception:  # noqa: BLE001 - 历史形态损坏时按「无差异」降级
        return None
