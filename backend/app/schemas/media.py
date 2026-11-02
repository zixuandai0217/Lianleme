"""媒体资产接口 Pydantic Schema。"""
import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MediaAssetResponse(BaseModel):
    """上传成功后的资产元数据（不含对象 key 与任何 URL）。"""
    asset_id: str = Field(..., description="不可猜测的资产标识")
    content_type: str
    size_bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    checksum: str = Field(..., description="服务端计算的 sha256 摘要")
    created_at: Optional[datetime.datetime] = None


class MediaAssetUrlResponse(BaseModel):
    """短时有效的原图签名链接及其元数据。"""
    asset_id: str
    kind: str
    url: str = Field(..., description="短时有效的签名 GET 链接")
    expires_at: datetime.datetime
    content_type: str
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: int
