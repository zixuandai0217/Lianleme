"""用户路由：邮箱认证、开发模式免登录、档案管理和 API Key 配置。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import ensure_current_user_matches, get_current_user
from app.models.user import User
from app.schemas.user import (
    ApiKeyConfigRequest,
    ApiKeyStatusResponse,
    EmailLoginRequest,
    LoginResponse,
    RegisterRequest,
    UserProfileUpdateRequest,
    UserResponse,
)
from app.services.user.user_service import UserService
from app.services.user.api_key_service import ApiKeyService

router = APIRouter()


def _build_user_response(user: User, api_key_status: ApiKeyStatusResponse | None) -> UserResponse:
    """Serialize a user model with its API key status for API responses."""
    return UserResponse(
        id=user.id,
        openid=user.openid,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        profile=user.profile,
        body_analysis=user.body_analysis,
        is_admin=bool(user.is_admin),
        api_key_status=api_key_status,
    )


@router.post("/register", response_model=LoginResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """邮箱注册：创建新用户并返回 token"""
    service = UserService(db)
    try:
        return await service.register(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auth/login", response_model=LoginResponse)
async def email_login(req: EmailLoginRequest, db: AsyncSession = Depends(get_db)):
    """邮箱密码登录"""
    service = UserService(db)
    try:
        return await service.email_login(req.email, req.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/dev-login", response_model=LoginResponse)
async def dev_login(db: AsyncSession = Depends(get_db)):
    """开发模式普通用户登录：自动创建或获取用户端体验账号。"""
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=403, detail="仅开发环境可用")
    service = UserService(db)
    return await service.dev_user_login()


@router.post("/dev-login/admin", response_model=LoginResponse)
async def dev_admin_login(db: AsyncSession = Depends(get_db)):
    """开发模式管理员登录：自动创建或获取管理端体验账号。"""
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=403, detail="仅开发环境可用")
    service = UserService(db)
    return await service.dev_admin_login()


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the authenticated user's profile using the bearer token identity."""
    key_service = ApiKeyService(db)
    api_key_status = await key_service.get_status(current_user.id)
    return _build_user_response(current_user, api_key_status)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取用户信息（含档案 + 体型分析结果 + API Key 状态）"""
    ensure_current_user_matches(current_user, user_id)
    service = UserService(db)
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    key_service = ApiKeyService(db)
    api_key_status = await key_service.get_status(user_id)
    return _build_user_response(user, api_key_status)


@router.put("/{user_id}/profile", response_model=UserResponse)
async def update_profile(
    user_id: int,
    req: UserProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新用户健身档案"""
    ensure_current_user_matches(current_user, user_id)
    service = UserService(db)
    user = await service.update_profile(user_id, req)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserResponse.model_validate(user)


@router.post("/{user_id}/api-key", response_model=ApiKeyStatusResponse)
async def save_api_key(
    user_id: int,
    req: ApiKeyConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """保存用户自有 LLM API Key（AES-256 加密存储）"""
    ensure_current_user_matches(current_user, user_id)
    key_service = ApiKeyService(db)
    return await key_service.save_key(user_id, req.provider, req.api_key)


@router.delete("/{user_id}/api-key", response_model=ApiKeyStatusResponse)
async def delete_api_key(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """清除用户 API Key，并停用该用户的 AI 生成功能。"""
    ensure_current_user_matches(current_user, user_id)
    key_service = ApiKeyService(db)
    return await key_service.delete_key(user_id)
