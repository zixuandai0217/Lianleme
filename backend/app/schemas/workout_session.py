"""训练会话的对外形状（工单 22/23）。

视图里的派生字段（当前动作、组内进度、下一个动作、是否可打卡）全部由服务端算好，
前端只渲染，不做本地推算——刷新或换设备后看到的必须是同一份状态。
"""
import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

ExerciseStatus = Literal["pending", "completed", "skipped"]


class SessionExerciseView(BaseModel):
    """单个动作在会话中的进度视图。"""

    index: int
    order: int = Field(..., description="动作在计划中的序号（1 起）")
    name: str
    sets: int
    reps: str
    weight_suggestion: str
    tips: str
    rest_seconds: int
    completed_sets: int
    skipped: bool
    skip_reason: Optional[str] = None
    status: ExerciseStatus
    target_set_number: Optional[int] = Field(
        default=None, description="下一组序号（1 起）；动作已完成或跳过时为空"
    )


class SessionProgress(BaseModel):
    completed_sets: int
    total_sets: int
    percent: int = Field(..., ge=0, le=100, description="已练组数 / 计划总组数，百分比取整")


class WorkoutSessionView(BaseModel):
    """一次会话的完整可恢复状态。"""

    session_id: str
    user_id: int
    plan_id: Optional[int] = None
    status: str = Field(..., description="in_progress / completed / abandoned")
    session_date: datetime.date = Field(..., description="会话归属的本地日期（开始当天）")
    started_at: datetime.datetime
    last_activity_at: datetime.datetime
    progress: SessionProgress
    exercises: List[SessionExerciseView]
    current_exercise: Optional[SessionExerciseView] = None
    next_exercise: Optional[SessionExerciseView] = None
    finished: bool = Field(..., description="全部动作已处理完（完成或跳过）")
    can_checkin: bool = Field(..., description="全部动作处理完且会话仍在进行中时才能收尾打卡")


class StartSessionRequest(BaseModel):
    """开始训练：只传用户标识，动作来自当前计划。"""

    user_id: int


class CompleteSetRequest(BaseModel):
    """完成一组：以「动作序号 + 组序号」定位，重复提交同一组是幂等的。"""

    exercise_index: int = Field(..., ge=0)
    set_index: int = Field(..., ge=0)


class SkipExerciseRequest(BaseModel):
    """跳过动作：必须给原因（前端未选择不可提交）。"""

    exercise_index: int = Field(..., ge=0)
    reason: str = Field(..., min_length=1, max_length=200, description="跳过原因，用户可读")

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        """纯空白不算「带了原因」：拒绝空话，避免把空白写进明细。"""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("跳过原因不能为空")
        return cleaned
