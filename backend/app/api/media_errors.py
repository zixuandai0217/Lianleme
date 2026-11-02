"""媒体相关错误码与对用户的稳定文案（跨路由共享，避免同义副本）。

错误码是跨端契约（ADR-0008 §5）：码只在服务层定义一次，文案在这里定义一次；
上传接口与体型分析接口共用同一份，不允许各自再写一份措辞。
"""
from fastapi import HTTPException, status

from app.services.media.media_asset_service import (
    ERROR_CODE_ASSET_NOT_FOUND,
    ERROR_CODE_IMAGE_ANIMATED,
    ERROR_CODE_IMAGE_INVALID,
    ERROR_CODE_IMAGE_TOO_SMALL,
    ERROR_CODE_IMAGE_TYPE_MISMATCH,
    ERROR_CODE_PAYLOAD_TOO_LARGE,
    ERROR_CODE_STORAGE_UNAVAILABLE,
    ERROR_CODE_UNSUPPORTED_MEDIA_TYPE,
)

ERROR_CODE_CHECKSUM_MISMATCH = "checksum_mismatch"

# 同一错误码只有一条用户可见文案；底层异常细节只进日志。
MEDIA_ERROR_MESSAGES: dict[str, str] = {
    ERROR_CODE_ASSET_NOT_FOUND: "资产不存在或无权访问",
    ERROR_CODE_IMAGE_INVALID: "照片无法识别，请换一张清晰的图片",
    ERROR_CODE_STORAGE_UNAVAILABLE: "照片暂时无法保存，请稍后重试",
    ERROR_CODE_CHECKSUM_MISMATCH: "文件校验摘要不匹配，请重新上传",
    ERROR_CODE_UNSUPPORTED_MEDIA_TYPE: "不支持的图片格式，请上传 JPG、PNG 或 WebP",
    ERROR_CODE_PAYLOAD_TOO_LARGE: "图片超过大小上限，请压缩后重试",
    ERROR_CODE_IMAGE_ANIMATED: "暂不支持动图，请上传单张照片",
    ERROR_CODE_IMAGE_TYPE_MISMATCH: "图片内容与声明的格式不符",
    ERROR_CODE_IMAGE_TOO_SMALL: "图片分辨率过低，请靠近拍摄或换一张更清晰的照片",
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


def unsupported_media_type() -> HTTPException:
    """内容类型不在白名单：请求阶段拒绝，不产生资产或任务。"""
    return media_error(
        ERROR_CODE_UNSUPPORTED_MEDIA_TYPE, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    )


def payload_too_large() -> HTTPException:
    """原始字节超过上限：解码前拒绝，避免无谓的 CPU 与内存开销。"""
    return media_error(ERROR_CODE_PAYLOAD_TOO_LARGE, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)


def image_animated() -> HTTPException:
    """多帧或动图：本产品只接受单张全身照。"""
    return media_error(ERROR_CODE_IMAGE_ANIMATED, status.HTTP_400_BAD_REQUEST)


def image_type_mismatch() -> HTTPException:
    """声明的内容类型与实际文件头不一致（伪装成图片的文件）。"""
    return media_error(ERROR_CODE_IMAGE_TYPE_MISMATCH, status.HTTP_400_BAD_REQUEST)


def image_too_small() -> HTTPException:
    """最短边低于下限：提示用户靠近拍摄或换一张更清晰的照片。"""
    return media_error(ERROR_CODE_IMAGE_TOO_SMALL, status.HTTP_400_BAD_REQUEST)


# 上传校验错误码 → HTTP 状态：单一映射，避免路由层再维护一份 if/elif。
_UPLOAD_REJECTION_STATUS: dict[str, int] = {
    ERROR_CODE_UNSUPPORTED_MEDIA_TYPE: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    ERROR_CODE_PAYLOAD_TOO_LARGE: status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    ERROR_CODE_IMAGE_INVALID: status.HTTP_400_BAD_REQUEST,
    ERROR_CODE_IMAGE_ANIMATED: status.HTTP_400_BAD_REQUEST,
    ERROR_CODE_IMAGE_TYPE_MISMATCH: status.HTTP_400_BAD_REQUEST,
    ERROR_CODE_IMAGE_TOO_SMALL: status.HTTP_400_BAD_REQUEST,
}


def raise_upload_rejected(code: str) -> None:
    """把服务层的校验错误码转成 HTTP 响应；未登记的错误码按 400 兜底。"""
    raise media_error(code, _UPLOAD_REJECTION_STATUS.get(code, status.HTTP_400_BAD_REQUEST))
