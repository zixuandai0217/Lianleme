"""
通用响应模式
"""
from pydantic import BaseModel, Field
from typing import Optional, Any, List


class APIResponse(BaseModel):
    """通用 API 响应"""
    success: bool = True
    message: str = "操作成功"
    data: Optional[Any] = None


class PaginatedResponse(BaseModel):
    """分页响应"""
    success: bool = True
    message: str = "操作成功"
    data: List[Any] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
    has_next: bool = False


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: dict


class ErrorDetail(BaseModel):
    """错误详情"""
    code: str
    message: str
    details: Optional[List[dict]] = None
