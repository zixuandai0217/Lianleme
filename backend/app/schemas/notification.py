"""站内通知（收件箱）与提醒 tick 的对外形状（工单 33）。"""
import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class NotificationItem(BaseModel):
    """一条站内通知（由投递记录投影而来）。"""

    id: int
    rule_code: str = Field(..., description="触发这条通知的规则代码")
    title: str
    body: str
    target_path: str = Field(..., description="点击后应跳转的站内路径")
    created_at: datetime.datetime
    read_at: Optional[datetime.datetime] = None
    is_read: bool


class NotificationListResponse(BaseModel):
    """收件箱一页；``unread_count`` 是全量未读数，不是本页未读数。"""

    items: List[NotificationItem]
    total: int
    unread_count: int
    page: int
    page_size: int


class MarkReadResponse(BaseModel):
    notification_id: int
    read_at: datetime.datetime
    unread_count: int


class MarkAllReadResponse(BaseModel):
    updated: int
    unread_count: int


class TickSummaryResponse(BaseModel):
    """一次手动 tick 的摘要（内部/运维入口）。"""

    status: str
    evaluated_users: int
    delivered: int
    duplicates: int
    skipped: int = 0
    failed: int
    ran_at: datetime.datetime


class ReminderPreferenceResponse(BaseModel):
    """用户的提醒偏好（没有保存过时返回缺省值）。"""

    daily_training_enabled: bool
    rest_day_note_enabled: bool
    recall_inactive_enabled: bool
    weekly_goal_enabled: bool
    onboarding_nudge_enabled: bool
    quiet_hours_start: str
    quiet_hours_end: str
    daily_cap: int = Field(..., ge=0, le=5, description="每日最多投递条数 0-5")
    weekly_goal_target: int = Field(..., ge=1, le=14, description="每周训练目标次数")
    timezone: str


class ReminderPreferenceUpdate(BaseModel):
    """更新提醒偏好（整份替换；非法值在写入前被拒绝，已存偏好保持不变）。"""

    daily_training_enabled: bool = True
    rest_day_note_enabled: bool = False
    recall_inactive_enabled: bool = True
    weekly_goal_enabled: bool = True
    onboarding_nudge_enabled: bool = True
    quiet_hours_start: str = Field(
        default="22:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="免打扰开始 HH:MM"
    )
    quiet_hours_end: str = Field(
        default="08:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="免打扰结束 HH:MM"
    )
    daily_cap: int = Field(default=2, ge=0, le=5, description="每日最多投递条数 0-5")
    weekly_goal_target: int = Field(default=3, ge=1, le=14, description="每周训练目标次数")

    @model_validator(mode="after")
    def quiet_hours_must_differ(self) -> "ReminderPreferenceUpdate":
        if self.quiet_hours_start == self.quiet_hours_end:
            raise ValueError("免打扰开始与结束不能相同")
        return self


DeliveryStatus = Literal["sent", "skipped", "failed"]


class DeliveryRecordItem(BaseModel):
    """投递记录（运营排查用）：包含被跳过的候选及其原因。"""

    id: int
    user_id: int
    rule_code: str
    local_date: datetime.date
    channel: str
    status: DeliveryStatus
    skip_reason: Optional[str] = None
    created_at: datetime.datetime


class DeliveryRecordListResponse(BaseModel):
    items: List[DeliveryRecordItem]
    total: int
    page: int
    page_size: int


# ---------- Web Push 重通道（工单 35） ----------


class PushStatusResponse(BaseModel):
    """推送通道状态：服务端是否配置了密钥、当前身份是否已订阅。"""

    available: bool = Field(..., description="服务端 VAPID 配置齐全时为 true")
    subscribed: bool = Field(..., description="当前身份是否存在有效订阅")
    subscription_count: int = Field(..., ge=0, description="当前身份的有效订阅数")
    public_key: str | None = Field(
        default=None, description="VAPID 公钥；通道可用时浏览器用它完成订阅"
    )


class PushSubscribeKeys(BaseModel):
    """浏览器生成的订阅密钥（只用于加密推送载荷，服务端不打印）。"""

    p256dh: str = Field(..., min_length=1, max_length=255)
    auth: str = Field(..., min_length=1, max_length=255)

    @field_validator("p256dh", "auth")
    @classmethod
    def key_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("订阅密钥不能为空")
        return cleaned


class PushSubscribeRequest(BaseModel):
    """登记一台浏览器的推送订阅；endpoint 是幂等身份。"""

    endpoint: str = Field(..., min_length=1, max_length=2048)
    keys: PushSubscribeKeys

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("endpoint 不能为空")
        return cleaned


class PushSubscribeResponse(BaseModel):
    """登记结果：重复登记同一 endpoint 仍是同一行，重新激活。"""

    subscribed: bool = True
    subscription_id: int
    subscription_count: int = Field(..., ge=0)


class PushUnsubscribeResponse(BaseModel):
    """注销结果：只软失效本人订阅，返回本次失效的条数。"""

    subscribed: bool = False
    deactivated: int = Field(..., ge=0)
