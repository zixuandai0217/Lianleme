"""训练记录相关 Pydantic Schema"""
import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

PlanImpactStatus = Literal[
    "not_dispatched", "evaluating", "pending_choice", "applied", "failed"
]
RecoverySource = Literal["model", "fallback"]
ComparisonDirection = Literal["up", "down", "flat", "first_time"]


class FeedbackCompletion(BaseModel):
    """本次完成情况：完成率由服务端按会话明细计算。"""

    completed_sets: int
    total_sets: int
    completion_rate: float = Field(..., ge=0, le=1)
    duration_minutes: int


class FeedbackComparison(BaseModel):
    """与上一条打卡的对比；首次训练时数值为空、方向为 first_time。"""

    has_previous: bool
    previous_completion_rate: Optional[float] = Field(default=None, ge=0, le=1)
    delta_percent: Optional[float] = Field(
        default=None, description="完成率差值（百分点），不是相对百分比"
    )
    delta_points: Optional[float] = Field(
        default=None, description="delta_percent 的同义字段（规格里的百分点命名）"
    )
    direction: ComparisonDirection


class FeedbackRecovery(BaseModel):
    """恢复建议：模型生成或规则兜底，tips 永不为空。"""

    source: RecoverySource
    tips: List[str] = Field(..., min_length=1)


class FeedbackPlanImpact(BaseModel):
    """本次打卡对计划的影响：调整作业状态的投影，不是第二份结论存储。"""

    status: PlanImpactStatus
    job_id: Optional[str] = None
    direction: Optional[Literal["increase", "decrease", "keep"]] = None
    reason: str
    before_summary: Optional[str] = None
    after_summary: Optional[str] = None


class WorkoutFeedback(BaseModel):
    """四段式反馈报告：本次完成 / 对比 / 恢复建议 / 计划影响。"""

    completion: FeedbackCompletion
    comparison: FeedbackComparison
    recovery: FeedbackRecovery
    plan_impact: FeedbackPlanImpact


class WorkoutCompleteRequest(BaseModel):
    """训练完成上报请求"""
    user_id: int
    plan_id: Optional[int] = None
    workout_date: datetime.date
    total_sets: int
    completed_sets: int
    duration_minutes: int
    difficulty_rating: Optional[int] = Field(None, ge=1, le=5, description="用户自评难度 1-5")
    detail: Optional[dict] = Field(None, description="各动作完成详情 JSON")


class WorkoutRecordResponse(BaseModel):
    """训练记录响应。

    旧客户端继续读 ``id / workout_date / completion_rate / duration_minutes /
    ai_feedback / job_id / job_error``；新客户端读 ``feedback`` 的四段结构。
    没有 ``feedback`` 的历史记录在统计接口里照常可读（为 None）。
    """
    id: int
    workout_date: datetime.date
    completion_rate: float
    duration_minutes: int
    ai_feedback: Optional[str] = None
    # 打卡后投递的调整作业：响应不等待评估，只带稳定标识；没建成时给稳定原因。
    job_id: Optional[str] = Field(
        default=None, description="本次打卡触发的调整作业标识（不等待评估完成）"
    )
    job_error: Optional[str] = Field(
        default=None, description="作业未创建时的稳定原因，例如 job_not_created"
    )
    feedback: Optional[WorkoutFeedback] = Field(
        default=None, description="四段式反馈：完成 / 对比 / 恢复 / 计划影响"
    )

    class Config:
        from_attributes = True


class CheckInStatsResponse(BaseModel):
    """打卡统计响应"""
    total_checkins: int
    streak_days: int = Field(..., description="连续打卡天数")
    monthly_checkins: int
    monthly_completion_rate: float
    recent_records: List[WorkoutRecordResponse] = []
