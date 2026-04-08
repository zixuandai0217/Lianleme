"""体型分析相关 Pydantic Schema"""
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
    """体型分析接口响应"""
    task_id: str = Field(..., description="异步任务 ID，用于轮询结果")
    status: str = Field(default="processing")


class AnalyzeResultResponse(BaseModel):
    """体型分析结果轮询响应"""
    task_id: str
    status: str = Field(..., description="processing / completed / failed")
    result: Optional[BodyAnalysisResult] = None
    error: Optional[str] = None
