"""体重记录相关 Pydantic Schema"""
import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class WeightRecordCreate(BaseModel):
    """新增体重记录请求"""
    user_id: int
    weight: float = Field(..., gt=0, lt=500, description="体重 kg")
    recorded_date: Optional[datetime.date] = Field(None, description="记录日期，默认今天")
    note: Optional[str] = Field(None, max_length=200, description="备注")


class WeightRecordResponse(BaseModel):
    """体重记录响应"""
    id: int
    weight: float
    recorded_date: datetime.date
    note: Optional[str] = None
    created_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class WeightTrendResponse(BaseModel):
    """体重趋势响应：含历史记录 + 统计摘要"""
    records: List[WeightRecordResponse]
    total: int
    current_weight: Optional[float] = Field(None, description="最新体重")
    start_weight: Optional[float] = Field(None, description="最早记录体重")
    min_weight: Optional[float] = Field(None, description="历史最低")
    max_weight: Optional[float] = Field(None, description="历史最高")
    change: Optional[float] = Field(None, description="总变化量（最新 - 最早）")


class WeightExtreme(BaseModel):
    """窗口内的一个极值点（带日期，便于复盘）"""
    weight: float
    recorded_date: datetime.date


class WeightWindowInsight(BaseModel):
    """单个锚点窗口（最近 7 天 / 最近 30 天）的变化与极值"""
    days: int
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    sample_count: int = 0
    change: Optional[float] = Field(None, description="窗口内最后一条 - 第一条（1 位小数）")
    direction: str = Field("insufficient", description="down / up / flat / insufficient")
    min: Optional[WeightExtreme] = None
    max: Optional[WeightExtreme] = None
    insufficient: bool = Field(True, description="窗口内记录少于 2 条")


class WeightWeeklyComparison(BaseModel):
    """周对照：该周体重变化与训练天数并列（只做描述性对照）"""
    week_start: datetime.date
    week_end: datetime.date
    sample_count: int = 0
    weight_change: Optional[float] = None
    training_days: int = 0
    relation: str = Field(
        "insufficient",
        description="same / reverse / flat / insufficient，均相对最近 30 天方向",
    )


GoalMode = Literal["numeric", "direction", "none"]
GoalVerdict = Literal["on_track", "off_track", "steady", "insufficient", "neutral"]
GoalReason = Literal[
    "no_goal",
    "insufficient_samples",
    "change_matches_target",
    "change_against_target",
    "change_within_flat_band",
    "target_reached",
    "change_matches_goal_direction",
    "change_against_goal_direction",
    "hold_within_band",
    "drift_outside_band",
]
GoalExpectedDirection = Literal["down", "up", "hold"]


class WeightGoalInsight(BaseModel):
    """目标判定：数值目标优先，其次按健身目标方向推断，无目标时保持中性"""
    mode: GoalMode = Field("none", description="numeric / direction / none")
    verdict: GoalVerdict = Field(
        "neutral",
        description="on_track / off_track / steady / insufficient / neutral",
    )
    reason: GoalReason = Field("no_goal", description="稳定的判定码，由前端映射文案")
    gap: Optional[float] = Field(None, description="最新体重 - 目标体重（1 位小数）")
    target_weight: Optional[float] = Field(None, description="档案里的目标体重 kg")
    goal_label: Optional[str] = Field(None, description="档案健身目标原值")
    expected_direction: Optional[GoalExpectedDirection] = Field(
        None, description="期望方向：down / up / hold"
    )


class WeightInsightResponse(BaseModel):
    """体重趋势解读：锚点窗口 + 带日期极值 + 四周训练对照"""
    anchor_date: Optional[datetime.date] = Field(None, description="最新一条记录的日期")
    is_stale: bool = Field(False, description="锚点距今天超过 7 天")
    stale_days: int = 0
    windows: Dict[str, WeightWindowInsight] = Field(
        default_factory=dict, description="d7 / d30 两个窗口"
    )
    weekly: List[WeightWeeklyComparison] = []
    training_data_available: bool = Field(
        False, description="训练数据是否可读（读不到则周对照隐藏）"
    )
    goal: WeightGoalInsight = Field(default_factory=WeightGoalInsight)
