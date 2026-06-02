"""体重记录相关 Pydantic Schema"""
import datetime
from typing import List, Optional

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
