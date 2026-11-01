"""Behavior tests for anchor-based weight trend insights."""

import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.record import WorkoutRecord
from app.models.user import User
from app.models.weight import WeightRecord
from app.services.weight.weight_service import WeightService

FIXED_TODAY = datetime.date(2026, 3, 18)


def day(offset: int) -> datetime.date:
    """Return the fixed-today date shifted back by ``offset`` days."""
    return FIXED_TODAY - datetime.timedelta(days=offset)


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    """Create an isolated SQLite database for weight insight tests."""
    db_path = tmp_path / "weight-insights.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest_asyncio.fixture
async def users(session_factory):
    """Seed an owner and an unrelated user."""
    async with session_factory() as session:
        owner = User(openid="weight-owner", nickname="Owner")
        other = User(openid="weight-other", nickname="Other")
        session.add_all([owner, other])
        await session.commit()
        await session.refresh(owner)
        await session.refresh(other)
        return {"owner": owner, "other": other}


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


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    """Freeze the service clock so window boundaries are deterministic."""
    monkeypatch.setattr(WeightService, "_today", lambda self: FIXED_TODAY)


def _auth(user_id: int) -> dict[str, str]:
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def seed_weights(factory, user_id: int, items: list[tuple[datetime.date, float]]) -> None:
    async with factory() as session:
        for recorded_date, weight in items:
            session.add(
                WeightRecord(user_id=user_id, weight=weight, recorded_date=recorded_date)
            )
        await session.commit()


async def seed_workouts(factory, user_id: int, dates: list[datetime.date]) -> None:
    async with factory() as session:
        for workout_date in dates:
            session.add(
                WorkoutRecord(
                    user_id=user_id,
                    workout_date=workout_date,
                    total_sets=3,
                    completed_sets=3,
                    completion_rate=1.0,
                    duration_minutes=30,
                )
            )
        await session.commit()


async def fetch_insights(client: AsyncClient, user_id: int) -> dict:
    response = await client.get(f"/api/weight/{user_id}/insights", headers=_auth(user_id))
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_windows_anchor_on_latest_record_and_flag_stale(
    client: AsyncClient, session_factory, users
):
    """Windows are anchored on the newest record, not on today, and stale data is flagged."""
    owner = users["owner"]
    await seed_weights(session_factory, owner.id, [(day(20), 72.0), (day(10), 71.0)])

    data = await fetch_insights(client, owner.id)

    assert data["anchor_date"] == day(10).isoformat()
    assert data["is_stale"] is True
    assert data["stale_days"] == 10

    d7 = data["windows"]["d7"]
    assert d7["sample_count"] == 1
    assert d7["insufficient"] is True
    assert d7["change"] is None
    assert d7["direction"] == "insufficient"

    d30 = data["windows"]["d30"]
    assert d30["sample_count"] == 2
    assert d30["change"] == -1.0
    assert d30["direction"] == "down"
    assert d30["insufficient"] is False


@pytest.mark.asyncio
async def test_extremes_carry_dates_and_prefer_latest_on_tie(
    client: AsyncClient, session_factory, users
):
    """Min/max keep their dates and ties resolve to the most recent record."""
    owner = users["owner"]
    await seed_weights(
        session_factory,
        owner.id,
        [
            (day(5), 70.0),
            (day(3), 69.5),
            (day(2), 72.5),
            (day(1), 69.5),
            (day(0), 71.0),
        ],
    )

    data = await fetch_insights(client, owner.id)
    d7 = data["windows"]["d7"]

    assert d7["min"]["weight"] == 69.5
    assert d7["min"]["recorded_date"] == day(1).isoformat()
    assert d7["max"]["weight"] == 72.5
    assert d7["max"]["recorded_date"] == day(2).isoformat()


@pytest.mark.asyncio
async def test_single_record_has_no_change_but_keeps_extremes(
    client: AsyncClient, session_factory, users
):
    """One record yields an insufficient window without fabricating a change."""
    owner = users["owner"]
    await seed_weights(session_factory, owner.id, [(day(2), 70.0)])

    data = await fetch_insights(client, owner.id)

    assert data["anchor_date"] == day(2).isoformat()
    for key in ("d7", "d30"):
        window = data["windows"][key]
        assert window["sample_count"] == 1
        assert window["insufficient"] is True
        assert window["change"] is None
        assert window["min"]["weight"] == 70.0
        assert window["min"]["recorded_date"] == day(2).isoformat()


@pytest.mark.asyncio
async def test_no_records_returns_empty_insight(client: AsyncClient, users):
    """Without any record the endpoint returns an explicit empty shape."""
    owner = users["owner"]

    data = await fetch_insights(client, owner.id)

    assert data["anchor_date"] is None
    assert data["is_stale"] is False
    assert data["weekly"] == []
    assert data["training_data_available"] is False
    assert data["goal"]["mode"] == "none"
    for key in ("d7", "d30"):
        assert data["windows"][key]["insufficient"] is True
        assert data["windows"][key]["sample_count"] == 0


@pytest.mark.asyncio
async def test_same_day_resubmission_updates_one_sample(client: AsyncClient, users):
    """Same-day resubmission overwrites the record instead of adding a sample."""
    owner = users["owner"]
    when = day(2).isoformat()
    headers = _auth(owner.id)

    for weight in (70.0, 70.4):
        response = await client.post(
            "/api/weight/record",
            headers=headers,
            json={"user_id": owner.id, "weight": weight, "recorded_date": when},
        )
        assert response.status_code == 200

    data = await fetch_insights(client, owner.id)
    d7 = data["windows"]["d7"]

    assert d7["sample_count"] == 1
    assert d7["change"] is None
    assert d7["min"]["weight"] == 70.4
    assert d7["max"]["weight"] == 70.4


@pytest.mark.asyncio
async def test_weekly_comparison_pairs_weight_change_with_training_days(
    client: AsyncClient, session_factory, users
):
    """Four ISO weeks pair each week's weight change with distinct training days."""
    owner = users["owner"]
    await seed_weights(
        session_factory,
        owner.id,
        [
            (datetime.date(2026, 2, 24), 74.0),
            (datetime.date(2026, 2, 27), 73.5),
            (datetime.date(2026, 3, 3), 73.5),
            (datetime.date(2026, 3, 7), 73.9),
            (datetime.date(2026, 3, 10), 73.6),
            (datetime.date(2026, 3, 14), 73.6),
            (datetime.date(2026, 3, 16), 73.4),
            (datetime.date(2026, 3, 17), 73.4),
        ],
    )
    await seed_workouts(
        session_factory,
        owner.id,
        [
            datetime.date(2026, 2, 24),
            datetime.date(2026, 2, 26),
            datetime.date(2026, 3, 3),
            datetime.date(2026, 3, 16),
            datetime.date(2026, 3, 17),
        ],
    )

    data = await fetch_insights(client, owner.id)
    weekly = data["weekly"]

    assert data["anchor_date"] == "2026-03-17"
    assert data["training_data_available"] is True
    assert [week["week_start"] for week in weekly] == [
        "2026-02-23",
        "2026-03-02",
        "2026-03-09",
        "2026-03-16",
    ]
    assert [week["weight_change"] for week in weekly] == [-0.5, 0.4, 0.0, 0.0]
    assert [week["training_days"] for week in weekly] == [2, 1, 0, 2]
    assert [week["relation"] for week in weekly] == ["same", "reverse", "flat", "flat"]


@pytest.mark.asyncio
async def test_windows_cross_month_and_short_span_limits_weeks(
    client: AsyncClient, session_factory, users
):
    """The 30-day window crosses month boundaries and a short span yields fewer weeks."""
    owner = users["owner"]
    await seed_weights(
        session_factory,
        owner.id,
        [
            (day(46), 74.0),
            (day(45), 73.8),
            (day(26), 73.0),
            (day(1), 72.0),
        ],
    )

    data = await fetch_insights(client, owner.id)

    anchor = day(1)
    d30 = data["windows"]["d30"]
    assert d30["start_date"] == (anchor - datetime.timedelta(days=29)).isoformat()
    assert d30["end_date"] == anchor.isoformat()
    assert d30["sample_count"] == 2
    assert d30["change"] == -1.0
    assert data["weekly"][0]["week_start"] == "2026-02-23"
    assert data["weekly"][0]["week_end"] == "2026-03-01"


@pytest.mark.asyncio
async def test_short_record_span_renders_only_existing_weeks(
    client: AsyncClient, session_factory, users
):
    """A record span shorter than four weeks yields only the covered weeks."""
    owner = users["owner"]
    await seed_weights(
        session_factory,
        owner.id,
        [(datetime.date(2026, 3, 16), 72.0), (datetime.date(2026, 3, 17), 71.8)],
    )

    data = await fetch_insights(client, owner.id)

    assert [week["week_start"] for week in data["weekly"]] == ["2026-03-16"]


@pytest.mark.asyncio
async def test_training_source_failure_hides_weekly_only(
    client: AsyncClient, session_factory, users, monkeypatch
):
    """When training data cannot be read, weekly comparison hides and nothing else breaks."""
    owner = users["owner"]
    await seed_weights(
        session_factory,
        owner.id,
        [(datetime.date(2026, 3, 13), 73.0), (datetime.date(2026, 3, 17), 72.4)],
    )

    async def broken_training_dates(self, user_id, start, end):
        raise RuntimeError("training calendar unavailable")

    monkeypatch.setattr(WeightService, "_load_training_dates", broken_training_dates)

    data = await fetch_insights(client, owner.id)

    assert data["weekly"] == []
    assert data["training_data_available"] is False
    assert data["windows"]["d7"]["change"] == -0.6
    assert data["anchor_date"] == "2026-03-17"


@pytest.mark.asyncio
async def test_insights_are_owner_only(client: AsyncClient, users):
    """Insights follow the same owner-only guard as the rest of the weight routes."""
    owner = users["owner"]
    other = users["other"]

    forbidden = await client.get(f"/api/weight/{owner.id}/insights", headers=_auth(other.id))
    anonymous = await client.get(f"/api/weight/{owner.id}/insights")

    assert forbidden.status_code == 403
    assert anonymous.status_code == 401
