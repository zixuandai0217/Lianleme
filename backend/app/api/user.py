"""用户路由：微信登录、档案管理、API Key 配置"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import (
    ApiKeyConfigRequest,
    ApiKeyStatusResponse,
    LoginResponse,
    UserProfileUpdateRequest,
    UserResponse,
    WechatLoginRequest,
)
from app.services.user.user_service import UserService
from app.services.user.api_key_service import ApiKeyService

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def wechat_login(req: WechatLoginRequest, db: AsyncSession = Depends(get_db)):
    """微信登录：code 换取 openid，首次登录自动建档"""
    service = UserService(db)
    return await service.login(req.code)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """获取用户信息（含档案 + 体型分析结果 + API Key 状态）"""
    service = UserService(db)
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    key_service = ApiKeyService(db)
    api_key_status = await key_service.get_status(user_id)
    return UserResponse(
        id=user.id,
        openid=user.openid,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        profile=user.profile,
        body_analysis=user.body_analysis,
        api_key_status=api_key_status,
    )


@router.put("/{user_id}/profile", response_model=UserResponse)
async def update_profile(
    user_id: int, req: UserProfileUpdateRequest, db: AsyncSession = Depends(get_db)
):
    """更新用户健身档案"""
    service = UserService(db)
    user = await service.update_profile(user_id, req)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserResponse.model_validate(user)


@router.post("/{user_id}/api-key", response_model=ApiKeyStatusResponse)
async def save_api_key(
    user_id: int, req: ApiKeyConfigRequest, db: AsyncSession = Depends(get_db)
):
    """保存用户自有 LLM API Key（AES-256 加密存储）"""
    key_service = ApiKeyService(db)
    return await key_service.save_key(user_id, req.provider, req.api_key)


@router.delete("/{user_id}/api-key", response_model=ApiKeyStatusResponse)
async def delete_api_key(user_id: int, db: AsyncSession = Depends(get_db)):
    """清除用户 API Key，恢复使用系统默认 Key"""
    key_service = ApiKeyService(db)
    return await key_service.delete_key(user_id)
