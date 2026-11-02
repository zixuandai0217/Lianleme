"""姿态纠错会话与帧上行的对外形状（工单 40）。

帧批只接受关键点数据（坐标 + 可见度），**不接受任何图片或视频字段**；
响应里只有时间、计数与质量统计，从不回传关键点坐标（隐私是硬约束）。
"""

import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 机位视角词表：会话创建、切分配置与姿态图共用同一份定义。
CAMERA_VIEWS = frozenset({"front", "side"})
DEFAULT_CAMERA_VIEW = "front"

# MediaPipe Pose 输出的关键点上限（ADR-0002）
MAX_KEYPOINTS = 33
# 单批帧数上限：约 12 秒 @5fps，超过即拒绝，不静默截断
MAX_FRAMES_PER_BATCH = 60
MAX_PERSON_COUNT = 16
# 建议上传间隔：3-5 帧/秒（ADR-0002 数据流一节）
UPLOAD_INTERVAL_MS = 200

# 明确拒绝的媒体字段：姿态接口只收关键点，摄像头画面永不出设备。
_MEDIA_PAYLOAD_FIELDS = frozenset(
    {
        "image",
        "image_base64",
        "image_bytes",
        "image_file",
        "image_url",
        "video",
        "video_base64",
        "video_bytes",
        "video_file",
        "video_url",
        "frame_image",
        "frame_images",
        "jpeg_base64",
        "png_base64",
        "media",
        "media_asset_id",
        "audio",
        "audio_base64",
    }
)

CameraView = Literal["front", "side"]
CycleState = Literal["waiting", "completed"]
IssueSeverity = Literal["info", "warn", "critical"]
ActionSource = Literal["llm", "user"]
FeedbackSource = Literal["llm", "template"]

# 动作词表：模型识别与用户手选共用；未知动作一律 other。
ACTION_TYPES = ("squat", "deadlift", "other")
ActionName = Literal["squat", "deadlift", "other"]

# 降级原因的稳定词表（跨端契约）：前端据此决定文案与埋点，不允许自由文本。
PoseDegradeReason = Literal[
    "api_key_unavailable",
    "timeout",
    "rate_limited",
    "auth_failed",
    "unparsable",
    "provider_error",
    "budget_exhausted",
    "circuit_open",
]


class PoseAction(BaseModel):
    """动作判断：``source=llm`` 是模型识别，``source=user`` 是用户手动指定。"""

    name: ActionName
    confidence: float = Field(..., ge=0.0, le=1.0)
    source: ActionSource = "llm"


class PoseIssue(BaseModel):
    """一条规则问题项：类型、严重度、涉及关节与模板提示。"""

    type: str
    severity: IssueSeverity
    joints: List[str] = Field(default_factory=list)
    hint: str = ""


class PoseHighlight(BaseModel):
    """骨架高亮：severity 交给 UI 决定红色（critical）或橙色（warn / info）。"""

    joints: List[str] = Field(default_factory=list)
    segments: List[List[str]] = Field(default_factory=list, description="需要标色的关节连线")
    severity: IssueSeverity
    issue_type: str


class _StrictPosePayload(BaseModel):
    """姿态请求基类：未知字段一律拒绝，并给出稳定的媒体载荷错误码。"""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_media_payload(cls, data):
        """图片/视频字段不是「多余字段」，而是明确禁止的载荷，错误必须可读。"""
        if isinstance(data, dict):
            rejected = sorted(_MEDIA_PAYLOAD_FIELDS.intersection(data))
            if rejected:
                raise ValueError(
                    "pose_media_payload_rejected: 姿态会话只接受关键点数据，"
                    f"不接受图片或视频字段：{', '.join(rejected)}"
                )
        return data


class PoseKeypoint(BaseModel):
    """单个关键点：归一化坐标 + 可见度（MediaPipe Pose 输出形状）。

    有限数值与可见度区间由路由层统一校验：Pydantic 的校验错误会把原始值
    连同 NaN 一起回显，反而让 422 响应无法序列化，所以这里只做形状校验。
    """

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    z: float = 0.0
    visibility: float = 1.0


class PoseFrameIn(_StrictPosePayload):
    """一帧关键点数据。"""

    t_ms: int = Field(..., ge=0, description="相对会话开始的毫秒时间戳，单调不减")
    keypoints: List[PoseKeypoint] = Field(
        ...,
        min_length=1,
        max_length=MAX_KEYPOINTS,
        description=f"关键点数组，最多 {MAX_KEYPOINTS} 个",
    )
    person_count: int = Field(default=1, ge=0, le=MAX_PERSON_COUNT, description="画面中的人数")


class PoseFramesRequest(_StrictPosePayload):
    """一批帧；单批帧数上限由服务端显式校验（错误码可读，不静默截断）。"""

    frames: List[PoseFrameIn] = Field(..., min_length=1, description="帧数组，按 t_ms 递增")


class PoseSessionCreate(BaseModel):
    """创建会话的可选参数。"""

    model_config = ConfigDict(extra="forbid")

    camera_view: CameraView = Field(default="front", description="front：正面；side：正侧")
    exercise_hint: Optional[str] = Field(
        default=None, max_length=32, description="用户手动指定的动作（可选，优先于识别）"
    )


class PoseCycle(BaseModel):
    """一个已完成周期的对外结果：时间、质量统计与规则评估（无关键点坐标）。"""

    cycle_id: str
    start_ms: int
    end_ms: int
    duration_ms: int
    evaluable: bool = Field(..., description="False 表示不可评估：无评分，只给机位提示")
    visibility_ratio: float = Field(..., ge=0.0, le=1.0)
    out_of_frame_ratio: float = Field(..., ge=0.0, le=1.0)
    person_count: int
    reasons: List[str] = Field(default_factory=list, description="不可评估原因（稳定错误码）")
    camera_hint: Optional[str] = Field(default=None, description="不可评估时的机位提示")
    score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=10.0,
        description=(
            "最终质量分：规则问题主导，模型分只可下调；不可评估周期恒为空，绝不编造评分"
        ),
    )
    issues: List[PoseIssue] = Field(default_factory=list, description="规则问题项，按严重度排序")
    highlights: List[PoseHighlight] = Field(
        default_factory=list, description="与问题项一一对应的骨架高亮"
    )
    hint: Optional[str] = Field(
        default=None, description="一句主提示（至多一句补充）；无问题或去重抑制时为空"
    )
    action: Optional[PoseAction] = Field(
        default=None, description="动作判断；无模型且用户未指定时为空"
    )
    model_score: Optional[float] = Field(
        default=None, ge=0.0, le=10.0, description="模型给出的综合质量分（融合前）"
    )
    feedback_source: Optional[FeedbackSource] = Field(
        default=None, description="llm：模型改写；template：规则模板（降级路径）"
    )
    degraded: bool = Field(default=False, description="本周期是否降级为规则结果")
    degrade_reason: Optional[PoseDegradeReason] = Field(
        default=None, description="降级原因（稳定码）：timeout/rate_limited/auth_failed/..."
    )
    spoken: bool = Field(default=True, description="False 表示命中 20 秒去重窗口，不重复播报")
    notice: Optional[str] = Field(
        default=None, description="一次性会话提示（如「深度点评已暂停」），其余周期为空"
    )


class PoseFramesResponse(BaseModel):
    """追加帧的响应：本批新完成的周期 + 会话累计状态。"""

    accepted: int
    total_frames: int
    cycles_count: int
    cycle_state: CycleState
    cycles: List[PoseCycle] = Field(default_factory=list)


class PoseSessionResponse(BaseModel):
    """创建会话的响应。"""

    session_id: str
    camera_view: CameraView
    ttl_seconds: int
    expires_at: datetime.datetime
    upload_interval_ms: int = UPLOAD_INTERVAL_MS
    camera_hint: str


class PoseResultResponse(BaseModel):
    """取结果：会话至今完成的周期（只有统计，没有关键点）。"""

    session_id: str
    status: Literal["active", "finished"]
    cycle_state: CycleState
    cycles_count: int
    cycles: List[PoseCycle] = Field(default_factory=list)


class PoseFinishResponse(BaseModel):
    """结束会话的聚合摘要。"""

    session_id: str
    status: Literal["finished"] = "finished"
    cycles_count: int
    evaluable_cycles: int
    not_evaluable_cycles: int
    frames_total: int
    avg_quality: float = Field(
        default=0.0,
        description="已评估周期的平均质量分；quality_available=False 时不是真实评分",
    )
    issues_histogram: dict[str, int] = Field(default_factory=dict)
    quality_available: bool = False
    model_calls: int = Field(default=0, description="本会话模型调用次数")
    degraded_cycles: int = Field(default=0, description="降级为纯规则的周期数")
    model_degraded: bool = Field(default=False, description="本会话是否出现过模型降级")
    circuit_open: bool = Field(default=False, description="连续失败熔断：后续周期不再调用模型")
    model_paused: bool = Field(default=False, description="模型调用已达单会话上限")
    paused_notice_sent: bool = Field(default=False, description="「深度点评已暂停」是否已提示过")
