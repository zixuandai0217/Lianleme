"""JWT bearer auth dependencies and ownership guards."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def _raise_unauthorized(detail: str = "未登录或登录已过期") -> None:
    """Raise a standard bearer-auth unauthorized error."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a bearer token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        _raise_unauthorized()

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=["HS256"],
        )
    except JWTError:
        _raise_unauthorized()

    subject = payload.get("sub")
    if subject is None:
        _raise_unauthorized("无效的登录凭证")

    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        _raise_unauthorized("无效的登录凭证")

    user = await db.get(User, user_id)
    if user is None:
        _raise_unauthorized("用户不存在或登录已失效")

    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require the current user to be an admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


def ensure_current_user_matches(current_user: User, target_user_id: int) -> None:
    """Reject requests where the authenticated user and target user diverge."""
    if current_user.id != target_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问其他用户的数据",
        )
