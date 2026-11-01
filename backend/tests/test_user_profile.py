"""Route-level tests for the profile JSON container (target weight field)."""

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
    """Create an isolated SQLite database for profile tests."""
    db_path = tmp_path / "user-profile.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest_asyncio.fixture
async def user(session_factory):
    """Seed the profile owner."""
    async with session_factory() as session:
        owner = User(openid="profile-owner", nickname="Owner")
        session.add(owner)
        await session.commit()
        await session.refresh(owner)
        return owner


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


def _auth(user_id: int) -> dict[str, str]:
    """Build bearer auth headers for a specific user id."""
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_profile_round_trip_keeps_target_weight_and_existing_fields(
    client: AsyncClient, user
):
    """目标体重随档案一起保存，回读时与既有字段同时保留。"""
    profile = {
        "height": 178.0,
        "weight": 72.0,
        "goal": "减脂",
        "experience": "初级",
        "age": 30,
        "gender": "男",
        "target_weight": 68.0,
    }

    response = await client.put(
        f"/api/user/{user.id}/profile",
        headers=_auth(user.id),
        json={"profile": profile},
    )
    assert response.status_code == 200
    assert response.json()["profile"]["target_weight"] == 68.0

    fetched = await client.get(f"/api/user/{user.id}", headers=_auth(user.id))
    assert fetched.status_code == 200
    saved = fetched.json()["profile"]
    assert saved == profile
