"""媒体相关错误码与对用户的稳定文案（跨路由共享，避免同义副本）。

错误码是跨端契约（ADR-0008 §5）：码只在服务层定义一次，文案在这里定义一次；
上传接口与体型分析接口共用同一份，不允许各自再写一份措辞。
"""
from fastapi import HTTPException, status

from app.services.media.media_asset_service import (
    ERROR_CODE_ASSET_NOT_FOUND,
    ERROR_CODE_IMAGE_INVALID,
    ERROR_CODE_STORAGE_UNAVAILABLE,
)

ERROR_CODE_CHECKSUM_MISMATCH = "checksum_mismatch"

# 同一错误码只有一条用户可见文案；底层异常细节只进日志。
MEDIA_ERROR_MESSAGES: dict[str, str] = {
    ERROR_CODE_ASSET_NOT_FOUND: "资产不存在或无权访问",
    ERROR_CODE_IMAGE_INVALID: "照片无法识别，请换一张清晰的图片",
    ERROR_CODE_STORAGE_UNAVAILABLE: "照片暂时无法保存，请稍后重试",
    ERROR_CODE_CHECKSUM_MISMATCH: "文件校验摘要不匹配，请重新上传",
}


def media_error(code: str, status_code: int) -> HTTPException:
    """按错误码构造统一响应体 ``{"code","message"}``。"""
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": MEDIA_ERROR_MESSAGES[code]},
    )


def asset_not_found() -> HTTPException:
    """缺失、他人持有、已删除统一 404，不因存在性而不同，避免探测。"""
    return media_error(ERROR_CODE_ASSET_NOT_FOUND, status.HTTP_404_NOT_FOUND)


def image_invalid() -> HTTPException:
    """图片无法解码：请求阶段失败，绝不创建资产或任务。"""
    return media_error(ERROR_CODE_IMAGE_INVALID, status.HTTP_400_BAD_REQUEST)


def storage_unavailable() -> HTTPException:
    """对象存储不可用：明确失败，绝不回退为数据库内联内容。"""
    return media_error(
        ERROR_CODE_STORAGE_UNAVAILABLE, status.HTTP_503_SERVICE_UNAVAILABLE
    )


def checksum_mismatch() -> HTTPException:
    """客户端提供的摘要与服务端计算结果不一致。"""
    return media_error(ERROR_CODE_CHECKSUM_MISMATCH, status.HTTP_400_BAD_REQUEST)
