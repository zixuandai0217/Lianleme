"""管理后台相关 Pydantic Schema（只读运营视图，字段已脱敏）"""
import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.plan import PlanAdjustmentExplanation, PlanGenerationBasis

# 需关注标记：服务端规则计算，可同时存在，可被列表筛选
AdminUserFlag = Literal[
    "new_no_plan",
    "planned_no_checkin",
    "inactive_14d",
    "never_analyzed",
    "api_key_missing",
]

# 列表排序：固定枚举，不接受任意列名
AdminUserSort = Literal[
    "registered_asc",
    "registered_desc",
    "last_active_asc",
    "last_active_desc",
]


class AdminUserListItem(BaseModel):
    """用户列表单项：基础档案（已脱敏）+ 服务端派生字段。

    响应中不出现密码哈希、加密 API Key、原始 openid 或原始邮箱。
    """

    id: int
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    openid: str = Field(..., description="openid 掩码：前 6 后 4，长度不足则整段打码")
    email_masked: Optional[str] = Field(None, description="邮箱掩码：保留首字符与域名")
    is_admin: bool = False
    has_api_key: bool = Field(..., description="是否已配置自己的 LLM API Key（不返回密钥本身）")
    llm_provider: Optional[str] = Field(None, description="已配置时返回 provider 名称，否则为空")
    created_at: datetime.datetime

    # 派生字段：由固定数量的聚合查询一次算出
    has_plan: bool
    plan_difficulty_factor: Optional[float] = Field(None, description="最近一份计划的难度系数")
    total_checkins: int
    checkins_30d: int
    last_checkin_date: Optional[datetime.date] = None
    last_active_at: datetime.datetime = Field(
        ..., description="最近活跃时间：注册/计划/打卡/分析/体重/对话事件时间的最大值（非登录时间）"
    )
    days_since_last_checkin: Optional[int] = None
    flags: list[AdminUserFlag] = Field(default_factory=list)


class AdminUserListResponse(BaseModel):
    """用户列表分页响应"""

    items: list[AdminUserListItem]
    total: int
    page: int
    page_size: int


# 导出结果：成功，或因超过行数上限被拒绝（被拒同样写审计）
AdminExportOutcome = Literal["success", "rejected"]


class AdminExportAuditItem(BaseModel):
    """一次导出尝试的审计记录（只读；成功时 rejection_reason 为空）。"""

    id: int
    operator_id: int = Field(..., description="发起导出的管理员用户 ID")
    filter_summary: str = Field(..., description="规范化后的筛选条件摘要（含排序）")
    filter_hash: str = Field(..., description="筛选摘要短哈希，与下载文件名中的哈希一致")
    row_count: int = Field(..., description="成功时为导出行数；被拒时为若导出会有的行数")
    outcome: AdminExportOutcome
    rejection_reason: Optional[str] = Field(None, description="仅被拒时有值")
    created_at: datetime.datetime


class AdminExportAuditListResponse(BaseModel):
    """导出审计分页响应（按时间倒序）"""

    items: list[AdminExportAuditItem]
    total: int
    page: int
    page_size: int


# ── 用户详情聚合（工单 37）─────────────────────────────────────────────────────

# 详情分区：固定枚举。顺序就是响应里 ``sections`` 的回显顺序，也是请求省略时的全量集合。
AdminUserDetailSection = Literal[
    "profile",
    "body_analysis",
    "plan",
    "checkins",
    "weights",
    "timeline",
    "usage",
]

ADMIN_USER_DETAIL_SECTIONS: tuple[AdminUserDetailSection, ...] = (
    "profile",
    "body_analysis",
    "plan",
    "checkins",
    "weights",
    "timeline",
    "usage",
)

# 行为轨迹的事件类型：固定枚举，全部由既有记录派生（不引入埋点、没有登录会话表）。
AdminTimelineEventType = Literal[
    "registered",
    "first_body_analysis",
    "latest_body_analysis",
    "first_plan_generated",
    "latest_plan_adjustment",
    "first_checkin",
    "latest_checkin",
    "first_weight_record",
    "latest_weight_record",
    "latest_chat",
]

ADMIN_TIMELINE_EVENT_TYPES: tuple[AdminTimelineEventType, ...] = (
    "registered",
    "first_body_analysis",
    "latest_body_analysis",
    "first_plan_generated",
    "latest_plan_adjustment",
    "first_checkin",
    "latest_checkin",
    "first_weight_record",
    "latest_weight_record",
    "latest_chat",
)


class AdminBodyAnalysisSummary(BaseModel):
    """最近一次体型分析摘要；没有任何分析时整个分区为 null。"""

    body_type: Optional[str] = Field(
        default=None, description="体型分类：ectomorph / mesomorph / endomorph"
    )
    body_fat_range: Optional[str] = Field(default=None, description="体脂区间，如 '15-18%'")
    weak_muscles: Optional[list[str]] = Field(default=None, description="弱势肌群")
    strengths: Optional[list[str]] = Field(default=None, description="优势部位")
    summary: Optional[str] = Field(default=None, description="该次分析的结论摘要")
    analyzed_at: Optional[datetime.datetime] = Field(
        default=None, description="分析时间（UTC）；只有用户档案快照的老数据为空"
    )
    source: Optional[Literal["analysis_record", "profile_snapshot"]] = Field(
        default=None, description="数据来源：分析历史记录 / 用户档案上的最近一次快照"
    )


class AdminPlanDaySummary(BaseModel):
    """当前计划里的一天：给运营看的摘要，不含完整动作要领。"""

    day: int = Field(..., description="周几 1-7")
    focus: str = Field(..., description="训练重点")
    is_rest_day: bool = False
    exercise_count: int = 0
    total_sets: int = 0
    estimated_duration: int = 0


class AdminPlanSection(BaseModel):
    """当前计划 + 工单 20 的解释投影（生成依据与最近一次调整）；无计划时整个分区为 null。"""

    plan_id: int
    week_start: datetime.date
    difficulty_factor: float
    status: str
    week_structure: list[AdminPlanDaySummary] = Field(default_factory=list)
    generation: Optional[PlanGenerationBasis] = Field(
        default=None, description="生成依据：最近一次体型快照 + 当时的档案目标"
    )
    latest_adjustment: Optional[PlanAdjustmentExplanation] = Field(
        default=None, description="最近一次调整结论；null 表示这份计划从未被调整过"
    )


class AdminCheckinPoint(BaseModel):
    """近 90 天里的一次打卡。"""

    workout_date: datetime.date
    completion_rate: float
    duration_minutes: int
    difficulty_rating: Optional[int] = None


class AdminCheckinsSection(BaseModel):
    """打卡分区：近 90 天序列 + 连续天数 + 完成率分布（口径与用户自己的统计接口一致）。"""

    window_days: int = Field(90, description="序列窗口：含今天在内的 90 个自然日")
    series: list[AdminCheckinPoint] = Field(default_factory=list)
    streak_days: int = Field(0, description="连续打卡天数，与 GET /api/workout/{id}/stats 同口径")
    total_checkins: int = Field(0, description="累计打卡数（不限窗口），与用户统计接口一致")
    completion_rate_distribution: dict[str, int] = Field(
        default_factory=dict, description="窗口内完成率分布：0-49 / 50-79 / 80-100 三档计数"
    )


class AdminWeightPoint(BaseModel):
    """近 90 天里的一次体重记录。"""

    recorded_date: datetime.date
    weight: float


class AdminWeightsSection(BaseModel):
    """体重分区：近 90 天序列 + 记录频率。"""

    window_days: int = Field(90, description="序列窗口：含今天在内的 90 个自然日")
    series: list[AdminWeightPoint] = Field(default_factory=list)
    record_count: int = Field(0, description="窗口内的记录条数")
    records_per_week: float = Field(0.0, description="窗口内平均每周记录条数（保留两位小数）")
    latest_weight: Optional[float] = Field(default=None, description="窗口内最近一次体重（kg）")
    last_recorded_date: Optional[datetime.date] = Field(
        default=None, description="窗口内最近一次记录日期"
    )


class AdminTimelineEvent(BaseModel):
    """一条由既有数据派生的行为轨迹事件。"""

    type: AdminTimelineEventType
    occurred_at: datetime.datetime = Field(..., description="事件时间（UTC）")
    summary: str = Field(..., description="简短摘要")
    message: str = Field(..., description="可读文案")


class AdminTimelinePage(BaseModel):
    """行为轨迹分页响应（按时间倒序；只有注册也会有一条事件）。"""

    items: list[AdminTimelineEvent] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class AdminUsageSection(BaseModel):
    """AI 使用情况：只有 Key 状态与对话计数，不含任何消息内容或密钥。"""

    has_api_key: bool = Field(False, description="是否已配置自己的 LLM API Key")
    llm_provider: Optional[str] = Field(None, description="已配置时返回 provider 名称，否则为空")
    chat_message_count: int = Field(0, description="陪练对话消息总条数")
    user_message_count: int = Field(0, description="其中用户发出的条数")
    assistant_message_count: int = Field(0, description="其中 AI 回复的条数")
    last_chat_at: Optional[datetime.datetime] = Field(
        default=None, description="最近一条对话消息的时间（UTC）"
    )


class AdminUserDetailResponse(BaseModel):
    """用户详情聚合响应。

    只包含所请求的分区（未请求的键整个不出现）；请求了但数据源为空的分区为 null
    （``checkins`` / ``weights`` / ``timeline`` / ``usage`` 恒为对象，只是内容为空），
    所以「没请求」与「没有数据」可以区分。响应里不出现密码哈希、加密 Key、原始
    openid 或原始邮箱。
    """

    user_id: int
    sections: list[AdminUserDetailSection] = Field(
        default_factory=list, description="本次实际返回的分区（按固定枚举顺序）"
    )
    profile: Optional[AdminUserListItem] = Field(
        default=None, description="基础档案与账号状态（字段与列表项一致，已脱敏）"
    )
    body_analysis: Optional[AdminBodyAnalysisSummary] = None
    plan: Optional[AdminPlanSection] = None
    checkins: Optional[AdminCheckinsSection] = None
    weights: Optional[AdminWeightsSection] = None
    timeline: Optional[AdminTimelinePage] = None
    usage: Optional[AdminUsageSection] = None
