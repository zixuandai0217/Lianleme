"""管理后台相关 Pydantic Schema（只读运营视图，字段已脱敏）"""
import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

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
