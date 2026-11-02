"""媒体资产服务：请求期校验、对象 key 组织、去重、落库、缩略图与签名读图。"""
import asyncio
import base64
import binascii
import datetime
import hashlib
import io
import secrets
from dataclasses import dataclass

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import Storage
from app.models.media_asset import (
    ASSET_KIND_ORIGINAL,
    ASSET_KIND_THUMBNAIL,
    ASSET_STATUS_AVAILABLE,
    ASSET_STATUS_DEGRADED,
    MediaAsset,
)

# 与前端/接口共享的稳定错误码（上传校验、统一 404 与存储不可用语义）。
ERROR_CODE_ASSET_NOT_FOUND = "asset_not_found"
ERROR_CODE_IMAGE_INVALID = "image_invalid"
ERROR_CODE_STORAGE_UNAVAILABLE = "storage_unavailable"
ERROR_CODE_UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
ERROR_CODE_PAYLOAD_TOO_LARGE = "payload_too_large"
ERROR_CODE_IMAGE_ANIMATED = "image_animated"
ERROR_CODE_IMAGE_TYPE_MISMATCH = "image_type_mismatch"
ERROR_CODE_IMAGE_TOO_SMALL = "image_too_small"

# 扩展名只由内容类型决定，永远不使用用户原始文件名。
CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
# 白名单从扩展名映射派生，避免两处清单漂移。
# 白名单由配置决定；能力映射仍是扩展名与 Pillow 格式的唯一来源。
_DEFAULT_SUPPORTED_CONTENT_TYPES = frozenset(CONTENT_TYPE_EXTENSIONS)


def supported_content_types() -> frozenset[str]:
    """当前配置允许的内容类型（与可编码格式取交集）。"""
    configured = settings.allowed_media_content_types()
    return frozenset(configured) & _DEFAULT_SUPPORTED_CONTENT_TYPES
DEFAULT_CONTENT_TYPE = "application/octet-stream"
_DEFAULT_EXTENSION = ".bin"

# 存档时按声明格式重新编码；质量取高值，尽量保留原图观感。
_PILLOW_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_PILLOW_FORMAT_CONTENT_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
_ORIGINAL_REENCODE_QUALITY = 95

# 缩略图由原图 key 确定性派生：长边缩放、JPEG 质量取配置值。
THUMBNAIL_CONTENT_TYPE = "image/jpeg"

# 进程内降级计数：与 ``media.thumbnail.failed`` 事件一起满足「计数 + 事件」。
_thumbnail_degraded_total = 0


def _count_degraded_thumbnail() -> None:
    global _thumbnail_degraded_total
    _thumbnail_degraded_total += 1


def thumbnail_degraded_total() -> int:
    """本进程累计的缩略图降级次数（事件字段与测试用）。"""
    return _thumbnail_degraded_total
_THUMBNAIL_SUFFIX = ".thumb.jpg"


def utc_now() -> datetime.datetime:
    """当前 UTC 时间（带时区）。"""
    return datetime.datetime.now(datetime.timezone.utc)


class MediaValidationError(ValueError):
    """上传图片未通过请求期校验；``code`` 是稳定错误码，文案由接口层决定。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ThumbnailGenerationError(RuntimeError):
    """缩略图生成失败；``degraded_asset`` 是已经登记为降级的资产行。"""

    def __init__(self, degraded_asset: MediaAsset) -> None:
        super().__init__("缩略图生成失败")
        self.degraded_asset = degraded_asset


@dataclass(frozen=True)
class CleanedImage:
    """通过校验并清除了元数据的存档字节及其元数据。"""

    data: bytes
    content_type: str
    width: int
    height: int


def normalize_content_type(raw: str | None) -> str:
    """去掉参数并归一化内容类型；缺失时使用二进制默认值。"""
    if not raw:
        return DEFAULT_CONTENT_TYPE
    return raw.split(";", 1)[0].strip().lower() or DEFAULT_CONTENT_TYPE


def extension_for_content_type(content_type: str) -> str:
    """内容类型到对象 key 扩展名的稳定映射。"""
    return CONTENT_TYPE_EXTENSIONS.get(normalize_content_type(content_type), _DEFAULT_EXTENSION)


def validate_declared_content_type(content_type: str) -> str:
    """白名单校验：只接受 JPEG / PNG / WebP，其余一律拒绝。"""
    normalized = normalize_content_type(content_type)
    if normalized not in supported_content_types():
        raise MediaValidationError(ERROR_CODE_UNSUPPORTED_MEDIA_TYPE)
    return normalized


def validate_upload_size(size_bytes: int) -> None:
    """解码前按原始字节数拒绝超限上传，避免为超大文件做无谓解码。"""
    if size_bytes > settings.MEDIA_MAX_UPLOAD_BYTES:
        raise MediaValidationError(ERROR_CODE_PAYLOAD_TOO_LARGE)


def clean_image_bytes(data: bytes, declared_content_type: str) -> CleanedImage:
    """解码、校验单帧/最小边，按 EXIF 方向纠正后重新编码以清除全部元数据。

    校验顺序固定：解码失败 → 动图 → 声明与实际格式不符 → 最短边过低。
    存档字节只保留像素，EXIF（含 GPS）、ICC 与文本块都不会进入对象存储。
    """
    content_type = normalize_content_type(declared_content_type)
    pillow_format = _PILLOW_FORMATS[content_type]
    try:
        with Image.open(io.BytesIO(data)) as opened:
            opened.load()
            if (
                getattr(opened, "is_animated", False)
                or int(getattr(opened, "n_frames", 1) or 1) > 1
            ):
                raise MediaValidationError(ERROR_CODE_IMAGE_ANIMATED)
            actual_type = _PILLOW_FORMAT_CONTENT_TYPES.get(opened.format or "")
            if actual_type != content_type:
                raise MediaValidationError(ERROR_CODE_IMAGE_TYPE_MISMATCH)
            width, height = opened.size
            if min(width, height) < settings.MEDIA_MIN_EDGE_PX:
                raise MediaValidationError(ERROR_CODE_IMAGE_TOO_SMALL)
            cleaned = ImageOps.exif_transpose(opened)
    except MediaValidationError:
        raise
    except Exception:
        raise MediaValidationError(ERROR_CODE_IMAGE_INVALID) from None

    try:
        if pillow_format == "JPEG":
            if cleaned.mode not in {"RGB", "L"}:
                cleaned = cleaned.convert("RGB")
        elif pillow_format == "WEBP":
            if cleaned.mode not in {"RGB", "RGBA"}:
                cleaned = cleaned.convert(
                    "RGBA" if "A" in cleaned.mode or "transparency" in cleaned.info else "RGB"
                )
        elif cleaned.mode not in {"RGB", "RGBA", "L", "LA"}:
            cleaned = cleaned.convert(
                "RGBA" if "A" in cleaned.mode or "transparency" in cleaned.info else "RGB"
            )
    except Exception:
        raise MediaValidationError(ERROR_CODE_IMAGE_INVALID) from None

    # 丢弃 EXIF / GPS / ICC / 文本块等一切元数据，再编码为声明格式。
    cleaned.info.clear()
    buffer = io.BytesIO()
    save_options = {"quality": _ORIGINAL_REENCODE_QUALITY} if pillow_format != "PNG" else {}
    try:
        cleaned.save(buffer, format=pillow_format, **save_options)
    except Exception:
        raise MediaValidationError(ERROR_CODE_IMAGE_INVALID) from None

    return CleanedImage(
        data=buffer.getvalue(),
        content_type=content_type,
        width=cleaned.width,
        height=cleaned.height,
    )


def build_thumbnail_key(original_object_key: str) -> str:
    """缩略图 key 由原图 key 确定性派生，重复触发不会写出多份对象。"""
    return f"{original_object_key}{_THUMBNAIL_SUFFIX}"


def render_thumbnail(data: bytes) -> tuple[bytes, int, int]:
    """把长边精确缩放到配置值（放大或缩小），输出配置质量的 JPEG。

    契约要求「缩略图长边等于配置值」，因此不能用 ``Image.thumbnail``（它只缩不放）。
    """
    max_edge = max(1, settings.MEDIA_THUMBNAIL_MAX_EDGE_PX)
    with Image.open(io.BytesIO(data)) as opened:
        opened.load()
        image = ImageOps.exif_transpose(opened).convert("RGB")
    width, height = image.size
    if width >= height:
        target = (max_edge, max(1, round(height * max_edge / width)))
    else:
        target = (max(1, round(width * max_edge / height)), max_edge)
    if target != image.size:
        image = image.resize(target, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=settings.MEDIA_THUMBNAIL_JPEG_QUALITY,
    )
    return buffer.getvalue(), image.width, image.height


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

    async def find_thumbnail_by_key(self, object_key: str) -> MediaAsset | None:
        """按确定性 key 查找缩略图资产（包含降级行，重复生成时复用同一条）。"""
        result = await self._db.execute(
            select(MediaAsset).where(
                MediaAsset.object_key == object_key,
                MediaAsset.kind == ASSET_KIND_THUMBNAIL,
            )
        )
        return result.scalar_one_or_none()

    async def ensure_thumbnail(self, original: MediaAsset) -> MediaAsset:
        """生成并登记缩略图资产；目标对象或可用资产已存在时直接复用（幂等）。

        生成过程包在 savepoint 里：失败只回滚这次生成，不干扰调用方事务；随后登记一行
        ``degraded`` 缩略图资产并抛 ``ThumbnailGenerationError``，历史接口因此能返回
        「空 URL + 降级标记」而不是静默失败。
        """
        object_key = build_thumbnail_key(original.object_key)
        try:
            async with self._db.begin_nested():
                return await self._generate_thumbnail(original, object_key)
        except Exception as exc:
            # 失败路径也要落一行降级资产，否则历史接口无法区分「没缩略图」与「生成失败」。
            degraded = await self._save_thumbnail(original.user_id, object_key)
            _count_degraded_thumbnail()
            raise ThumbnailGenerationError(degraded) from exc

    async def _generate_thumbnail(
        self, original: MediaAsset, object_key: str
    ) -> MediaAsset:
        """生成或复用缩略图对象与资产行；失败由调用方降级。"""
        user_id = original.user_id
        existing = await self.find_thumbnail_by_key(object_key)
        if (
            existing is not None
            and existing.status == ASSET_STATUS_AVAILABLE
            and await self._storage.exists(object_key)
        ):
            return existing
        if await self._storage.exists(object_key):
            # 对象已存在但行丢失/降级：读回对象元数据并复用，不重复写入。
            data = await self._storage.read(object_key)
            width, height = await asyncio.to_thread(inspect_image_size, data)
            return await self._save_thumbnail(
                user_id, object_key, data=data, width=width, height=height
            )
        source = await self.read(original)
        data, width, height = await asyncio.to_thread(render_thumbnail, source)
        await self._storage.write(object_key, data, THUMBNAIL_CONTENT_TYPE)
        return await self._save_thumbnail(
            user_id, object_key, data=data, width=width, height=height
        )

    async def _save_thumbnail(
        self,
        user_id: int,
        object_key: str,
        *,
        data: bytes | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> MediaAsset:
        """写入/更新缩略图资产行；``data`` 为空表示降级占位（不写对象）。"""
        available = data is not None
        asset = await self.find_thumbnail_by_key(object_key)
        if asset is None:
            asset = MediaAsset(
                asset_id=generate_asset_id(),
                user_id=user_id,
                kind=ASSET_KIND_THUMBNAIL,
                object_key=object_key,
                content_type=THUMBNAIL_CONTENT_TYPE,
                size_bytes=0,
                checksum="",
                status=ASSET_STATUS_DEGRADED,
            )
            self._db.add(asset)
        asset.status = ASSET_STATUS_AVAILABLE if available else ASSET_STATUS_DEGRADED
        if available:
            payload = data or b""
            asset.size_bytes = len(payload)
            asset.width = width
            asset.height = height
            asset.checksum = sha256_hex(payload)
        else:
            asset.size_bytes = 0
            asset.width = None
            asset.height = None
            asset.checksum = ""
        await self._db.flush()
        return asset
