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


class CleanupCountsResponse(BaseModel):
    """清理结果计数：删掉多少对象、多少资产行、用了几个批次。

    ``batches`` 是本次调用提交的批次数，用来证明清理是分批而不是一个长事务；
    重复执行同一清理返回全零（幂等）。
    """
    deleted_objects: int = Field(..., description="本次从对象存储删除的对象数")
    deleted_assets: int = Field(..., description="本次标记为已删除的资产行数")
    batches: int = Field(..., description="本次提交的批次数")


class OrphanSweepResponse(BaseModel):
    """一次孤儿巡检的结果计数（单批、可重入）。"""
    scanned: int = Field(..., description="本批检查的未被引用对象数")
    deleted_orphans: int = Field(..., description="超过宽限期被删除的孤儿对象数")
    degraded_assets: int = Field(..., description="对象缺失、被标记降级的资产数")
    batches: int = Field(..., description="本次提交的批次数")
    skipped_young: int = Field(..., description="仍在宽限期内、保持不动的孤儿对象数")
