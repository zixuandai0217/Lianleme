"""训练计划相关 Pydantic Schema"""
import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.adjustment import AdjustmentDirection

# 今日状态的稳定枚举：前端仅凭该字段即可分叉，不再用「有没有 exercises」猜语义。
TodayWorkoutStatus = Literal["training_day", "rest_day", "no_plan"]


class Exercise(BaseModel):
    """单个训练动作"""
    name: str = Field(..., description="动作名称，如 '卧推'")
    sets: int = Field(..., ge=1, description="组数")
    reps: str = Field(..., description="次数或时长，如 '8-12' 或 '30s'")
    weight_suggestion: str = Field(..., description="重量建议，如 '体重 40%'")
    tips: str = Field(..., description="动作要领简述")
    rest_seconds: int = Field(default=60, description="组间休息秒数")


class DailyWorkout(BaseModel):
    """单日训练计划"""
    day: int = Field(..., ge=1, le=7, description="周几 1-7")
    focus: str = Field(..., description="训练重点，如 '胸背'")
    exercises: List[Exercise]
    estimated_duration: int = Field(..., description="预计时长（分钟）")
    is_rest_day: bool = Field(default=False, description="是否休息日")


class TrainingPlanSchema(BaseModel):
    """完整周训练计划"""
    id: Optional[int] = None
    user_id: int
    week_start: datetime.date
    weekly_plan: List[DailyWorkout]
    difficulty_factor: float = 1.0
    status: str = "active"


class GeneratePlanRequest(BaseModel):
    """生成训练计划请求"""
    user_id: int
    body_analysis: Optional[dict] = None
    profile: Optional[dict] = None
    week_start: Optional[datetime.date] = None


class PlanGenerationBasis(BaseModel):
    """计划生成依据：当次的体型分析快照 + 生成时的档案快照。

    每个子字段都可空：旧计划的快照里没有分析时间、没有档案目标，缺失即为 null，
    由前端决定降级文案；这里不编造默认值。``captured_at`` 是快照被计划捕获的时间
    （分析结果本身不带时间戳），旧计划为空表示「分析时间未知」。
    """

    body_type: Optional[str] = Field(
        default=None, description="体型分类：ectomorph / mesomorph / endomorph"
    )
    body_fat_range: Optional[str] = Field(default=None, description="体脂区间，如 '18-22%'")
    weak_muscles: Optional[List[str]] = Field(default=None, description="弱势肌群")
    strengths: Optional[List[str]] = Field(default=None, description="优势部位")
    analysis_summary: Optional[str] = Field(default=None, description="该次分析的结论摘要")
    captured_at: Optional[datetime.datetime] = Field(
        default=None, description="该次分析快照被捕获的时间（UTC）；旧计划为空"
    )
    profile_goal: Optional[str] = Field(
        default=None, description="生成时的档案目标；缺失表示无法定位"
    )


class PlanAdjustmentExplanation(BaseModel):
    """最近一次自动调整的说明。

    计划行只保存对调整结论记录的引用，内容是读取时投影出来的，不复制理由文本——
    结论的唯一事实源是调整记录本身。
    """

    direction: AdjustmentDirection = Field(..., description="increase / decrease / keep")
    trigger: Literal["completion_rate"] = Field(
        default="completion_rate", description="触发指标：当前只有完成率"
    )
    completion_rate: float = Field(..., ge=0, le=1, description="触发时的完成率 0-1")
    occurred_at: datetime.datetime = Field(..., description="调整发生时间（UTC）")
    reason: str = Field(..., description="调整链路产出的一句人话理由（含触发数值）")
    before_summary: Optional[str] = Field(
        default=None, description="调整前计划摘要（与打卡反馈同源：作业的计划差异快照）"
    )
    after_summary: Optional[str] = Field(
        default=None, description="调整后计划摘要（与打卡反馈同源：作业的计划差异快照）"
    )


class PlanExplanation(BaseModel):
    """计划解释：为什么这样练。

    两部分都可空：旧计划既没有生成快照也没有调整记录，读取仍然成功，两个子对象
    均为 null。``latest_adjustment`` 为 null 表示「没有调整记录」，与方向 keep 的
    真实调整可区分。
    """

    generation: Optional[PlanGenerationBasis] = Field(default=None, description="生成依据")
    latest_adjustment: Optional[PlanAdjustmentExplanation] = Field(
        default=None, description="最近一次调整；null 表示尚未调整"
    )


class PlanResponse(BaseModel):
    """训练计划响应"""
    plan: TrainingPlanSchema
    message: str = "训练计划生成成功"
    explanation: Optional[PlanExplanation] = Field(
        default=None, description="解释字段：生成依据 + 最近一次调整；旧计划两部分为空"
    )


class TodayWorkoutResponse(BaseModel):
    """今日训练三态响应。

    ``status`` 是唯一判定入口：training_day 带动作清单与汇总，rest_day 带恢复文案、
    no_plan 两者都不带。旧字段（``is_rest_day`` / ``day`` / ``focus`` / ``exercises``）
    继续保留：老调用方读不到清单时自然会走空态分支，不会被误判成训练日。
    """
    status: TodayWorkoutStatus = Field(..., description="training_day / rest_day / no_plan")
    is_rest_day: bool = Field(default=False, description="是否休息日；无计划时恒为 false")
    day: Optional[int] = Field(default=None, description="周几 1-7；无计划时为空")
    focus: Optional[str] = Field(default=None, description="训练重点")
    exercises: Optional[List[Exercise]] = Field(default=None, description="仅在训练日返回")
    estimated_duration: Optional[int] = Field(default=None, description="预计时长（分钟）")
    exercise_count: Optional[int] = Field(default=None, description="动作数量（仅训练日）")
    total_sets: Optional[int] = Field(default=None, description="计划总组数（仅训练日）")
    plan_id: Optional[int] = Field(default=None, description="计划标识（有可用计划时）")
    message: Optional[str] = Field(default=None, description="休息日恢复提示；无计划时不返回")
