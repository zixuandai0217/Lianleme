"""Auth guard regression tests for owner-only and admin-only routes."""

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


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    """Create an isolated SQLite database for auth guard tests."""
    db_path = tmp_path / "auth-guards.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_users(session_factory):
    """Seed a normal user, another user, and an admin user."""
    async with session_factory() as session:
        normal_user = User(openid="user-1", nickname="User One", is_admin=False)
        other_user = User(openid="user-2", nickname="User Two", is_admin=False)
        admin_user = User(openid="admin-1", nickname="Admin", is_admin=True)
        session.add_all([normal_user, other_user, admin_user])
        await session.commit()
        await session.refresh(normal_user)
        await session.refresh(other_user)
        await session.refresh(admin_user)
        return {
            "normal": normal_user,
            "other": other_user,
            "admin": admin_user,
        }


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
async def test_missing_token_is_rejected(client: AsyncClient, seeded_users):
    """Protected routes should reject requests without bearer auth."""
    user = seeded_users["normal"]

    response = await client.get(f"/api/user/{user.id}")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_cannot_read_another_user_profile(client: AsyncClient, seeded_users):
    """A user token should not unlock someone else's profile."""
    user = seeded_users["normal"]
    other = seeded_users["other"]

    response = await client.get(
        f"/api/user/{other.id}",
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_can_read_own_profile(client: AsyncClient, seeded_users):
    """A user token should allow reading the matching profile."""
    user = seeded_users["normal"]

    response = await client.get(
        f"/api/user/{user.id}",
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 200
    assert response.json()["id"] == user.id


@pytest.mark.asyncio
async def test_current_user_endpoint_returns_authenticated_user(client: AsyncClient, seeded_users):
    """The current-user endpoint should resolve identity from the bearer token."""
    user = seeded_users["normal"]

    response = await client.get(
        "/api/user/me",
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 200
    assert response.json()["id"] == user.id


@pytest.mark.asyncio
async def test_request_body_user_id_must_match_token(client: AsyncClient, seeded_users):
    """Body-carried user ids must match the authenticated user."""
    user = seeded_users["normal"]
    other = seeded_users["other"]

    response = await client.post(
        "/api/weight/record",
        headers=_auth_headers(user.id),
        json={"user_id": other.id, "weight": 70.5},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_access_admin_stats(client: AsyncClient, seeded_users):
    """Non-admin users must be rejected from admin endpoints."""
    user = seeded_users["normal"]

    response = await client.get(
        f"/api/admin/stats?user_id={user.id}",
        headers=_auth_headers(user.id),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_access_admin_stats(client: AsyncClient, seeded_users):
    """Admin users should be able to access admin stats."""
    admin_user = seeded_users["admin"]

    response = await client.get(
        f"/api/admin/stats?user_id={admin_user.id}",
        headers=_auth_headers(admin_user.id),
    )

    assert response.status_code == 200
    assert response.json()["total_users"] == 3


@pytest.mark.asyncio
async def test_dev_login_returns_non_admin_user(client: AsyncClient):
    """The default development login should land in the user surface."""
    response = await client.post("/api/user/dev-login")

    assert response.status_code == 200

    me = await client.get(
        "/api/user/me",
        headers={"Authorization": f"Bearer {response.json()['token']}"},
    )

    assert me.status_code == 200
    assert me.json()["is_admin"] is False


@pytest.mark.asyncio
async def test_dev_admin_login_returns_admin_user(client: AsyncClient):
    """The admin development login should use a dedicated admin identity."""
    response = await client.post("/api/user/dev-login/admin")

    assert response.status_code == 200

    me = await client.get(
        "/api/user/me",
        headers={"Authorization": f"Bearer {response.json()['token']}"},
    )

    assert me.status_code == 200
    assert me.json()["is_admin"] is True
