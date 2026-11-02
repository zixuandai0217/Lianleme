"""媒体资产服务：对象 key 组织、去重、落库与签名读图。"""
import base64
import binascii
import datetime
import hashlib
import io
import secrets

from PIL import Image
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import Storage
from app.models.media_asset import (
    ASSET_KIND_ORIGINAL,
    ASSET_STATUS_AVAILABLE,
    MediaAsset,
)

# 与前端/接口共享的稳定错误码（统一 404 与存储不可用语义）。
ERROR_CODE_ASSET_NOT_FOUND = "asset_not_found"
ERROR_CODE_IMAGE_INVALID = "image_invalid"
ERROR_CODE_STORAGE_UNAVAILABLE = "storage_unavailable"

# 扩展名只由内容类型决定，永远不使用用户原始文件名。
CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
DEFAULT_CONTENT_TYPE = "application/octet-stream"
_DEFAULT_EXTENSION = ".bin"


def utc_now() -> datetime.datetime:
    """当前 UTC 时间（带时区）。"""
    return datetime.datetime.now(datetime.timezone.utc)


def normalize_content_type(raw: str | None) -> str:
    """去掉参数并归一化内容类型；缺失时使用二进制默认值。"""
    if not raw:
        return DEFAULT_CONTENT_TYPE
    return raw.split(";", 1)[0].strip().lower() or DEFAULT_CONTENT_TYPE


def extension_for_content_type(content_type: str) -> str:
    """内容类型到对象 key 扩展名的稳定映射。"""
    return CONTENT_TYPE_EXTENSIONS.get(normalize_content_type(content_type), _DEFAULT_EXTENSION)


def generate_asset_id() -> str:
    """生成不可猜测的资产标识，同时作为对象 key 的一部分。"""
    return "as_" + secrets.token_urlsafe(16)


def build_object_key(
    user_id: int,
    asset_id: str,
    content_type: str,
    created_at: datetime.datetime | None = None,
) -> str:
    """对象 key：``{env}/{user_id}/{YYYYMM}/{asset_id}{ext}``。

    环境与用户前缀让用户级清理可枚举；原始文件名不参与 key，避免路径注入与隐私泄漏。
    """
    moment = created_at or utc_now()
    return (
        f"{settings.APP_ENV.strip('/')}/{user_id}/{moment:%Y%m}/"
        f"{asset_id}{extension_for_content_type(content_type)}"
    )


def sha256_hex(data: bytes) -> str:
    """计算服务端内容摘要（去重与完整性核对）。"""
    return hashlib.sha256(data).hexdigest()


def decode_base64_image(value: str) -> bytes:
    """解码内联图片；兼容 ``data:image/...;base64,`` 前缀。

    兼容期内联内容来自既有客户端，不能因为缺少补齐字符就拒绝；这里只要求能还原
    出非空字节，能否成为图片由上传接口的完整校验矩阵负责。
    """
    payload = value.strip()
    if payload.startswith("data:") and "," in payload:
        payload = payload.split(",", 1)[1].strip()
    if not payload:
        raise ValueError("图片 base64 为空")
    payload += "=" * (-len(payload) % 4)
    try:
        return base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("图片 base64 无法解码") from exc


def sniff_content_type(data: bytes) -> str:
    """按文件头识别常见图片类型，识别失败时回退为二进制。"""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return DEFAULT_CONTENT_TYPE


def inspect_image_size(data: bytes) -> tuple[int, int]:
    """用 Pillow 完整解码，返回宽高；无法解码时抛异常（由调用方转成 400）。"""
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
        image.verify()
    return width, height


class MediaAssetService:
    """资产读写入口；业务代码只依赖本服务与存储端口。"""

    def __init__(self, db: AsyncSession, storage: Storage) -> None:
        self._db = db
        self._storage = storage

    async def find_available_original(self, user_id: int, checksum: str) -> MediaAsset | None:
        """按用户 + 摘要查找仍可用的原图资产（去重）。"""
        result = await self._db.execute(
            select(MediaAsset)
            .where(
                MediaAsset.user_id == user_id,
                MediaAsset.kind == ASSET_KIND_ORIGINAL,
                MediaAsset.checksum == checksum,
                MediaAsset.status == ASSET_STATUS_AVAILABLE,
            )
            .order_by(MediaAsset.created_at)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_original(
        self,
        *,
        user_id: int,
        data: bytes,
        content_type: str,
        checksum: str,
        width: int | None,
        height: int | None,
        original_filename: str | None = None,
    ) -> MediaAsset:
        """写入对象存储并登记资产元数据；调用方负责提交事务。

        先写对象再落库：存储不可用时抛 ``StorageError``，数据库里不会留下资产行。
        （user_id, checksum）上有「可用原图」部分唯一索引兜住并发重复上传——撞键时
        删掉本次多写的对象并复用既有资产。
        """
        asset_id = generate_asset_id()
        normalized_type = normalize_content_type(content_type)
        object_key = build_object_key(user_id, asset_id, normalized_type)
        await self._storage.write(object_key, data, normalized_type)
        asset = MediaAsset(
            asset_id=asset_id,
            user_id=user_id,
            kind=ASSET_KIND_ORIGINAL,
            object_key=object_key,
            content_type=normalized_type,
            size_bytes=len(data),
            width=width,
            height=height,
            checksum=checksum,
            status=ASSET_STATUS_AVAILABLE,
            original_filename=(original_filename or None),
        )
        try:
            async with self._db.begin_nested():
                self._db.add(asset)
                await self._db.flush()
        except IntegrityError:
            # 并发的同摘要上传已落库：删掉本次刚写的对象，复用既有资产。
            await self._storage.delete(object_key)
            existing = await self.find_available_original(user_id, checksum)
            if existing is None:
                raise
            return existing
        return asset

    async def get_available_owned(self, asset_id: str, user_id: int) -> MediaAsset | None:
        """取本人可用的资产；不存在、已删除、他人持有都返回 None（不区分存在性）。"""
        result = await self._db.execute(
            select(MediaAsset).where(
                MediaAsset.asset_id == asset_id,
                MediaAsset.user_id == user_id,
                MediaAsset.status == ASSET_STATUS_AVAILABLE,
            )
        )
        return result.scalar_one_or_none()

    async def get_available_assets(
        self, asset_ids: set[str], user_id: int
    ) -> dict[str, MediaAsset]:
        """批量读取本人仍可用的资产，供历史/详情接口按需签名。

        归属过滤放在查询里：调用方拿不到他人资产，也就没有「先取再检查」漏判的机会。
        """
        if not asset_ids:
            return {}
        result = await self._db.execute(
            select(MediaAsset).where(
                MediaAsset.asset_id.in_(asset_ids),
                MediaAsset.user_id == user_id,
                MediaAsset.status == ASSET_STATUS_AVAILABLE,
            )
        )
        return {asset.asset_id: asset for asset in result.scalars().all()}

    async def sign(self, asset: MediaAsset) -> tuple[str, datetime.datetime]:
        """签发短时原图链接；URL 与过期时间只出现在响应里，不落库。"""
        return await self._storage.sign(
            asset.object_key,
            settings.MEDIA_SIGNED_URL_TTL_SECONDS,
        )

    async def read(self, asset: MediaAsset) -> bytes:
        """读取资产内容（分析执行等内部路径使用）。"""
        return await self._storage.read(asset.object_key)
