"""对象存储端口：业务代码只依赖这五个异步操作，不持有客户端、不拼访问地址。

真实实现（MinIO）把每个阻塞调用隔离到线程池；测试与本地开发使用内存实现。
访问地址只能通过 ``sign`` 获得短时有效的签名链接，bucket 始终保持私有。

维护路径额外需要一次「枚举」：孤儿巡检要拿对象清单与资产表比对。它是本模块的
第六个操作（``list_objects``），**不属于 §7 的五个业务操作契约**：请求路径上的
上传 / 读取 / 签名 / 删除 / 存在性检查仍然只依赖前五个，枚举仅供清理与巡检调用。
"""
import asyncio
import datetime
import io
import logging
import secrets
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from minio import Minio
from minio.error import S3Error
from urllib3 import PoolManager, Timeout

from app.core.config import settings

logger = logging.getLogger(__name__)

# 内存实现的签名 URL 前缀；对业务而言它是不透明地址，只有测试能解析。
IN_MEMORY_URL_PREFIX = "memory://media/"

# 签名过期后再次使用统一抛这个异常（端口级语义，不暴露底层细节）。
class StorageError(RuntimeError):
    """对象存储不可用，或签名链接已失效。"""


@dataclass(frozen=True)
class StoredObject:
    """枚举结果：对象 key 与其年龄（秒）。

    年龄由存储层给出（MinIO 用 ``last_modified``，内存实现用可推进时钟），
    清理侧只比较它与宽限期，不自己猜对象寿命。
    """

    key: str
    age_seconds: float


class Storage(Protocol):
    """业务层唯一可见的对象存储契约。"""

    async def write(self, key: str, data: bytes, content_type: str) -> None:
        """写入对象；已存在时覆盖。"""

    async def read(self, key: str) -> bytes:
        """读取对象内容（仅服务端校验、分析执行与巡检使用）。"""

    async def sign(self, key: str, ttl_seconds: int) -> tuple[str, datetime.datetime]:
        """签发短时 GET 链接，返回 (url, 过期时间)。"""

    async def delete(self, key: str) -> None:
        """删除对象；对象不存在时视为成功。"""

    async def exists(self, key: str) -> bool:
        """对象是否存在。"""

    async def list_objects(self, prefix: str) -> list[StoredObject]:
        """列举前缀下的对象及其年龄（仅维护巡检使用，不属于业务五操作）。"""


class MinioStorage:
    """MinIO 实现：所有阻塞网络调用都放进线程池，避免阻塞事件循环。"""

    def __init__(self, client: Minio, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def write(self, key: str, data: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.put_object,
                self._bucket,
                key,
                io.BytesIO(data),
                len(data),
                content_type=content_type,
            )
        except Exception as exc:  # 端口边界统一收敛成 StorageError
            raise StorageError("对象写入失败") from exc

    async def read(self, key: str) -> bytes:
        def _read() -> bytes:
            response = self._client.get_object(self._bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        try:
            return await asyncio.to_thread(_read)
        except Exception as exc:
            raise StorageError("对象读取失败") from exc

    async def sign(self, key: str, ttl_seconds: int) -> tuple[str, datetime.datetime]:
        ttl = max(1, int(ttl_seconds))
        try:
            url = await asyncio.to_thread(
                self._client.presigned_get_object,
                self._bucket,
                key,
                expires=datetime.timedelta(seconds=ttl),
            )
        except Exception as exc:
            raise StorageError("签名链接生成失败") from exc
        return url, _utc_now() + datetime.timedelta(seconds=ttl)

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(self._client.remove_object, self._bucket, key)
        except Exception as exc:
            raise StorageError("对象删除失败") from exc

    async def exists(self, key: str) -> bool:
        def _exists() -> bool:
            try:
                self._client.stat_object(self._bucket, key)
            except S3Error as exc:
                if exc.code in {"NoSuchKey", "NoSuchObject", "NotFound"}:
                    return False
                raise
            return True

        try:
            return await asyncio.to_thread(_exists)
        except Exception as exc:
            raise StorageError("对象状态查询失败") from exc

    async def list_objects(self, prefix: str) -> list[StoredObject]:
        """列举前缀下的对象；年龄取自对象存储的 ``last_modified``。"""

        def _list() -> list[StoredObject]:
            now = _utc_now()
            found: list[StoredObject] = []
            # list_objects 是惰性生成器：迭代过程必须整体留在工作线程里。
            for item in self._client.list_objects(
                self._bucket, prefix=prefix, recursive=True
            ):
                modified = item.last_modified
                if modified is not None and modified.tzinfo is None:
                    modified = modified.replace(tzinfo=datetime.timezone.utc)
                age = 0.0 if modified is None else max(0.0, (now - modified).total_seconds())
                found.append(StoredObject(key=item.object_name, age_seconds=age))
            return found

        try:
            return await asyncio.to_thread(_list)
        except Exception as exc:
            raise StorageError("对象列举失败") from exc


class InMemoryStorage:
    """内存实现：测试与本地开发使用，签名链接会随时间失效。

    ``clock`` 可注入（默认 ``time.monotonic``），测试通过 ``advance`` 推进时钟即可
    断言「同一 URL 过期后不可再用」，无需等待真实时间。
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._offset = 0.0
        self._objects: dict[str, tuple[bytes, str]] = {}
        # 对象写入时刻（同一时钟）：枚举年龄与「宽限期内不清理」断言都靠它。
        self._written_at: dict[str, float] = {}
        # token -> (object key, 失效时刻)；URL 本身不暴露 key。
        self._signed: dict[str, tuple[str, float]] = {}

    @property
    def object_count(self) -> int:
        """当前对象数量（测试断言去重不新增对象）。"""
        return len(self._objects)

    def advance(self, seconds: float) -> None:
        """推进内存时钟，用于验证签名过期语义。"""
        self._offset += seconds

    def _now(self) -> float:
        return self._clock() + self._offset

    async def write(self, key: str, data: bytes, content_type: str) -> None:
        self._objects[key] = (data, content_type)
        self._written_at[key] = self._now()

    async def read(self, key: str) -> bytes:
        try:
            return self._objects[key][0]
        except KeyError as exc:
            raise StorageError("对象不存在") from exc

    async def sign(self, key: str, ttl_seconds: int) -> tuple[str, datetime.datetime]:
        if key not in self._objects:
            raise StorageError("对象不存在")
        ttl = max(1, int(ttl_seconds))
        token = secrets.token_urlsafe(24)
        self._signed[token] = (key, self._now() + ttl)
        return (
            f"{IN_MEMORY_URL_PREFIX}{token}",
            _utc_now() + datetime.timedelta(seconds=ttl),
        )

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)
        self._written_at.pop(key, None)
        expired = [token for token, (stored, _) in self._signed.items() if stored == key]
        for token in expired:
            self._signed.pop(token, None)

    async def exists(self, key: str) -> bool:
        return key in self._objects

    async def list_objects(self, prefix: str) -> list[StoredObject]:
        """按内存时钟返回对象年龄；``advance`` 推进后年龄随之增长。"""
        now = self._now()
        return [
            StoredObject(
                key=key,
                age_seconds=max(0.0, now - self._written_at.get(key, now)),
            )
            for key in self._objects
            if key.startswith(prefix)
        ]

    async def fetch(self, url: str) -> bytes:
        """解析签名 URL（仅内存实现提供，用于验证链接真实可用与过期语义）。"""
        token = url.removeprefix(IN_MEMORY_URL_PREFIX)
        signed = self._signed.get(token)
        if signed is None:
            raise StorageError("签名链接无效")
        key, expires_at = signed
        if expires_at <= self._now():
            self._signed.pop(token, None)
            raise StorageError("签名链接已过期")
        return await self.read(key)


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# 模块级单例客户端
_client: Minio | None = None
_storage: Storage | None = None


def get_minio_client() -> Minio:
    """返回 MinIO 客户端单例"""
    global _client
    if _client is None:
        _client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ROOT_USER,
            secret_key=settings.MINIO_ROOT_PASSWORD,
            secure=False,  # 本地开发不使用 TLS
        )
    return _client


def ensure_bucket_exists() -> None:
    """启动时确保 bucket 存在，不存在则自动创建；连接失败不阻断启动"""
    try:
        client = get_minio_client()
        bucket = settings.MINIO_BUCKET
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
    except Exception as e:
        logger.warning("MinIO 不可用，跳过 bucket 初始化: %s", e)


def build_storage() -> Storage:
    """在装配处决定端口实现。

    开发环境使用 SQLite（本地轻量运行、无 MinIO）时装配内存实现，避免每次开发运行
    都依赖外部服务；其余环境一律使用 MinIO。测试通过依赖覆盖注入自己的内存实例。
    """
    if settings.APP_ENV == "development" and settings.DATABASE_URL.startswith("sqlite"):
        return InMemoryStorage()
    return MinioStorage(get_minio_client(), settings.MINIO_BUCKET)


def get_storage() -> Storage:
    """FastAPI 依赖：返回进程级存储端口（装配处唯一入口）。"""
    global _storage
    if _storage is None:
        _storage = build_storage()
    return _storage


@contextmanager
def bounded_minio_client(timeout_seconds: float) -> Iterator[Minio]:
    """短超时、无重试的探测客户端（就绪检查专用）。

    asyncio 的超时只能取消「等待」，取消不了阻塞 socket 调用；复用共享客户端会让
    挂掉的存储把连接一直占住。这里按探测超时构造独立连接池，退出时清空。
    """
    transport = PoolManager(timeout=Timeout(total=timeout_seconds), retries=False)
    try:
        yield Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ROOT_USER,
            secret_key=settings.MINIO_ROOT_PASSWORD,
            secure=False,
            http_client=transport,
        )
    finally:
        transport.clear()
