"""MinIO 对象存储客户端：初始化 bucket、提供文件上传封装"""
from minio import Minio
from minio.error import S3Error

from app.core.config import settings

# 模块级单例客户端
_client: Minio | None = None


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
        import logging
        logging.getLogger(__name__).warning("MinIO 不可用，跳过 bucket 初始化: %s", e)


def upload_bytes(object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """上传字节数据到 MinIO，返回对象访问 URL"""
    import io
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET
    client.put_object(
        bucket_name=bucket,
        object_name=object_name,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return f"http://{settings.MINIO_ENDPOINT}/{bucket}/{object_name}"
