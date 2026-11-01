"""体型分析相关 Pydantic Schema"""
import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """体型分析请求：传入图片 base64 + 用户档案"""
    image_base64: str = Field(..., description="图片 base64 编码")
    user_id: int
    profile: Optional[dict] = Field(None, description="用户档案（身高体重目标等）")


class BodyAnalysisResult(BaseModel):
    """体型分析结构化输出（PydanticOutputParser 目标格式）"""
    body_type: str = Field(..., description="体型分类: ectomorph/mesomorph/endomorph")
    body_fat_range: str = Field(..., description="估算体脂区间，如 '15-20%'")
    weak_muscles: List[str] = Field(..., description="弱势肌群列表")
    strengths: List[str] = Field(..., description="优势部位列表")
    muscle_scores: dict = Field(default_factory=dict, description="各部位评分 0-10，用于雷达图")
    summary: str = Field(..., description="AI 文字总结建议")


class AnalyzeResponse(BaseModel):
    """体型分析接口响应（创建任务）"""
    task_id: str = Field(..., description="异步任务 ID，用于轮询结果")
    status: str = Field(default="pending", description="pending / processing")
    stage: str = Field(default="queued", description="queued / vision / parse / persist / done")
    created_at: Optional[datetime.datetime] = None
    expires_at: Optional[datetime.datetime] = None
    poll_interval_ms: int = Field(default=2000, description="建议轮询间隔（毫秒）")
    suggested_poll_interval_ms: Optional[int] = Field(
        default=None, description="建议轮询间隔别名，兼容既有前端"
    )


class AnalyzeErrorResponse(BaseModel):
    """对用户可见的、经过分类与脱敏的任务失败原因"""
    code: str = Field(..., description="稳定错误码")
    message: str = Field(..., description="安全文案，不包含供应商原文")
    retryable: bool = False


class AnalyzeResultResponse(BaseModel):
    """体型分析结果轮询响应（五态任务）"""
    task_id: str
    status: str = Field(..., description="pending / processing / completed / failed / expired")
    stage: str = Field(default="queued")
    attempt: int = 0
    progress: int = 0
    result: Optional[BodyAnalysisResult] = None
    error: Optional[AnalyzeErrorResponse] = None
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    expires_at: Optional[datetime.datetime] = None


class BodyAnalysisRecordResponse(BaseModel):
    """单条体型分析历史记录"""
    id: int
    image_thumbnail: Optional[str] = None
    result: BodyAnalysisResult
    created_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class BodyAnalysisHistoryResponse(BaseModel):
    """体型分析历史列表"""
    records: List[BodyAnalysisRecordResponse]
    total: int
