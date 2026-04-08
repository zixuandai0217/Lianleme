"""图片工具：base64 编码/解码、压缩处理"""
import base64
import io
from pathlib import Path
from typing import Union

from PIL import Image


def file_to_base64(file_path: Union[str, Path]) -> str:
    """将本地图片文件转为 base64 字符串"""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def bytes_to_base64(data: bytes) -> str:
    """将图片字节数据转为 base64 字符串"""
    return base64.b64encode(data).decode("utf-8")


def base64_to_bytes(b64: str) -> bytes:
    """base64 字符串转字节"""
    return base64.b64decode(b64)


def compress_image(b64: str, max_size_kb: int = 500, max_dimension: int = 1280) -> str:
    """
    压缩图片至目标大小与分辨率
    - max_size_kb: 最大文件大小（KB）
    - max_dimension: 最大宽/高像素
    """
    img_bytes = base64.b64decode(b64)
    img = Image.open(io.BytesIO(img_bytes))

    # 缩放到最大边不超过 max_dimension
    width, height = img.size
    if max(width, height) > max_dimension:
        ratio = max_dimension / max(width, height)
        new_size = (int(width * ratio), int(height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    # 转为 RGB（兼容 PNG 透明通道）
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # 逐步降低质量直到满足大小要求
    quality = 85
    while quality > 20:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= max_size_kb * 1024:
            break
        quality -= 10

    return base64.b64encode(buf.getvalue()).decode("utf-8")
