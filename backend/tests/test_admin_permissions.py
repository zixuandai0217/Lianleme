"""管理端权限回归（工单 39）：逐端点锁定「未登录 401 / 非管理员 403 / 管理员 200」。

身份只来自 bearer token：URL / 查询串 / 请求体里的 user_id 既不参与鉴权，也不能
把非管理员变成管理员。这些端点本来就有守卫，本文件只把契约钉死，防止后续新增或
重构管理端路由时悄悄漏掉一条。

覆盖端点：概览（stats）、用户列表、用户详情、CSV 导出、导出审计。
"""

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.user import User

# (可读名, 路径模板)；详情端点需要真实用户 ID，模板占位符统一替换。
ADMIN_ENDPOINTS = [
    ("overview", "/api/admin/stats"),
    ("user-list", "/api/admin/users"),
    ("user-detail", "/api/admin/users/{user_id}"),
    ("export", "/api/admin/users/export"),
    ("export-audits", "/api/admin/export-audits"),
]
ENDPOINT_IDS = [name for name, _ in ADMIN_ENDPOINTS]


def endpoint_path(template: str, user_id: int) -> str:
    """Materialize the detail placeholder with a real user id."""
    return template.format(user_id=user_id)


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    """Create an isolated SQLite database for the permission matrix."""
    db_path = tmp_path / "admin-permissions.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_users(session_factory):
    """Seed exactly one admin and one ordinary user."""
    async with session_factory() as session:
        normal_user = User(openid="perm-normal-user", nickname="普通用户", is_admin=False)
        admin_user = User(openid="perm-admin-user", nickname="管理员", is_admin=True)
        session.add_all([normal_user, admin_user])
        await session.commit()
        await session.refresh(normal_user)
        await session.refresh(admin_user)
        return {"normal": normal_user, "admin": admin_user}


@pytest_asyncio.fixture
async def client(session_factory):
    """Create an app client backed by the isolated test database."""

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as async_client:
        yield async_client

    app.dependency_overrides.clear()


def _auth_headers(user_id: int) -> dict[str, str]:
    """Build bearer auth headers for a specific user id."""
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
@pytest.mark.parametrize("name,template", ADMIN_ENDPOINTS, ids=ENDPOINT_IDS)
async def test_admin_endpoint_requires_authentication(
    client: AsyncClient, seeded_users, name: str, template: str
):
    """Every admin endpoint rejects an anonymous request with 401."""
    path = endpoint_path(template, seeded_users["normal"].id)

    response = await client.get(path)

    assert response.status_code == 401, f"{name} must return 401 without a token"


@pytest.mark.asyncio
@pytest.mark.parametrize("name,template", ADMIN_ENDPOINTS, ids=ENDPOINT_IDS)
async def test_admin_endpoint_rejects_non_admin(
    client: AsyncClient, seeded_users, name: str, template: str
):
    """Every admin endpoint returns 403 for an authenticated non-admin, even for their own id."""
    normal_user = seeded_users["normal"]
    path = endpoint_path(template, normal_user.id)

    response = await client.get(path, headers=_auth_headers(normal_user.id))

    assert response.status_code == 403, f"{name} must return 403 for a non-admin"


@pytest.mark.asyncio
@pytest.mark.parametrize("name,template", ADMIN_ENDPOINTS, ids=ENDPOINT_IDS)
async def test_admin_endpoint_allows_admin(
    client: AsyncClient, seeded_users, name: str, template: str
):
    """Every admin endpoint stays reachable for an admin, so the guard is not a blanket 403."""
    admin_user = seeded_users["admin"]
    path = endpoint_path(template, seeded_users["normal"].id)

    response = await client.get(path, headers=_auth_headers(admin_user.id))

    assert response.status_code == 200, f"{name} must return 200 for an admin"
