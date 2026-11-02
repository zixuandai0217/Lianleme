"""Admin user directory contract tests: search / filters / flags / sort / paging / masking.

These tests pin the external HTTP contract of ``GET /api/admin/users`` only. They do
not assert ORM internals or SQL text, with the single exception of the AC4 query
count guard, which observes emitted statements instead of asserting their wording.
"""

import datetime as dt
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.body_analysis import BodyAnalysisRecord
from app.models.chat_message import ChatMessageRecord
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.user import User
from app.models.weight import WeightRecord
from app.services.admin import user_directory

FIXED_NOW = dt.datetime(2026, 6, 15, 12, 0, tzinfo=dt.timezone.utc)
TODAY = FIXED_NOW.date()


def moment(days_ago: int, hour: int = 12) -> dt.datetime:
    """Return a fixed-clock instant shifted back by ``days_ago`` days."""
    return (FIXED_NOW - dt.timedelta(days=days_ago)).replace(hour=hour)


def day(days_ago: int) -> dt.date:
    """Return the fixed-clock date shifted back by ``days_ago`` days."""
    return TODAY - dt.timedelta(days=days_ago)


@pytest_asyncio.fixture
async def engine_and_factory(tmp_path: Path):
    """Create an isolated SQLite database plus the engine used by the app."""
    db_path = tmp_path / "admin-users.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine, factory

    await engine.dispose()


@pytest_asyncio.fixture
async def engine(engine_and_factory):
    """Expose the test engine so the query-count test can listen to statements."""
    return engine_and_factory[0]


@pytest_asyncio.fixture
async def session_factory(engine_and_factory):
    """Expose the bound session factory for seeding."""
    return engine_and_factory[1]


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
def frozen_clock(monkeypatch):
    """Freeze the directory clock so day boundaries are deterministic."""
    monkeypatch.setattr(user_directory, "utc_now", lambda: FIXED_NOW)


@pytest_asyncio.fixture
async def directory(session_factory):
    """Seed one admin plus users that each trigger a distinct set of attention flags."""
    async with session_factory() as session:
        admin = User(
            openid="wx-admin-openid-0001",
            email="admin@lianleme.test",
            nickname="管理员",
            is_admin=True,
            created_at=moment(40),
            llm_provider="openai",
            llm_api_key="enc::admin-ciphertext",
        )
        active = User(
            openid="wx-zhangsan-abcdef1234",
            email="zhangsan@example.com",
            password_hash="argon2-hash-secret",
            nickname="张三",
            created_at=moment(100),
            llm_provider="qwen",
            llm_api_key="enc::zhangsan-ciphertext",
        )
        new_no_plan = User(
            openid="wx-newbie-00",
            email="newbie@example.com",
            nickname="新用户",
            created_at=moment(8),
        )
        planned = User(
            openid="uid-planned-01",
            email="planned@example.com",
            nickname="有计划没打卡",
            created_at=moment(60),
            llm_provider="openai",
            llm_api_key="enc::planned-ciphertext",
        )
        inactive = User(
            openid="wx-inactive-789",
            email="inactive@example.com",
            nickname="很久没来了",
            created_at=moment(90),
            llm_provider="openai",
            llm_api_key="enc::inactive-ciphertext",
        )
        never_analyzed = User(
            openid="wx-noanalysis01",
            email="noanalysis@example.com",
            nickname="没做分析",
            created_at=moment(10),
            llm_provider="qwen",
            llm_api_key="enc::never-ciphertext",
        )
        api_key_missing = User(
            openid="uid9",
            email="nokey@example.com",
            nickname="没配Key",
            created_at=moment(25),
        )
        fresh = User(
            openid="wx-lisi-xyz",
            email="lisi@example.com",
            nickname="李四",
            created_at=moment(1),
        )
        session.add_all(
            [
                admin,
                active,
                new_no_plan,
                planned,
                inactive,
                never_analyzed,
                api_key_missing,
                fresh,
            ]
        )
        await session.commit()
        for user in (
            admin,
            active,
            new_no_plan,
            planned,
            inactive,
            never_analyzed,
            api_key_missing,
            fresh,
        ):
            await session.refresh(user)

        plan_specs = [
            (admin, 1.0, moment(38)),
            (active, 1.25, moment(10)),
            (planned, 1.5, moment(30)),
            (inactive, 1.1, moment(80)),
            (never_analyzed, 1.0, moment(9)),
            (api_key_missing, 1.05, moment(20)),
        ]
        for user, factor, created_at in plan_specs:
            session.add(
                TrainingPlan(
                    user_id=user.id,
                    week_start=created_at.date(),
                    weekly_plan={"days": []},
                    difficulty_factor=factor,
                    status="active",
                    created_at=created_at,
                )
            )

        checkin_specs = [
            (admin, day(1), moment(1, hour=8)),
            (admin, day(6), moment(6, hour=8)),
            (active, day(1), moment(1, hour=8)),
            (active, day(5), moment(5, hour=8)),
            (active, day(40), moment(40, hour=8)),
            (planned, day(9), moment(9, hour=8)),
            (inactive, day(20), moment(20, hour=8)),
            (never_analyzed, day(2), moment(2, hour=8)),
            (api_key_missing, day(1), moment(1, hour=8)),
        ]
        for user, workout_date, created_at in checkin_specs:
            session.add(
                WorkoutRecord(
                    user_id=user.id,
                    workout_date=workout_date,
                    total_sets=10,
                    completed_sets=8,
                    completion_rate=0.8,
                    duration_minutes=45,
                    created_at=created_at,
                )
            )

        analysis_specs = [
            (admin, moment(2)),
            (active, moment(3)),
            (planned, moment(20)),
            (inactive, moment(70)),
            (api_key_missing, moment(18)),
        ]
        for user, created_at in analysis_specs:
            session.add(
                BodyAnalysisRecord(
                    user_id=user.id,
                    result={"body_type": "mesomorph"},
                    created_at=created_at,
                )
            )

        session.add(
            WeightRecord(
                user_id=active.id,
                weight=72.5,
                recorded_date=day(2),
                created_at=moment(2),
            )
        )
        session.add(
            WeightRecord(
                user_id=never_analyzed.id,
                weight=80.0,
                recorded_date=day(5),
                created_at=moment(5),
            )
        )
        session.add(
            ChatMessageRecord(
                user_id=active.id,
                role="user",
                content="yo coach",
                created_at=moment(1, hour=9),
            )
        )

        await session.commit()
        return {
            "admin": admin,
            "active": active,
            "new_no_plan": new_no_plan,
            "planned": planned,
            "inactive": inactive,
            "never_analyzed": never_analyzed,
            "api_key_missing": api_key_missing,
            "fresh": fresh,
        }


@pytest_asyncio.fixture
async def many_users(session_factory):
    """Seed more users than one page so page_size=1 and page_size=20 both apply."""
    async with session_factory() as session:
        admin = User(
            openid="wx-bulk-admin",
            email="bulk-admin@lianleme.test",
            nickname="bulk-admin",
            is_admin=True,
            created_at=moment(200),
        )
        users = [
            User(
                openid=f"wx-bulk-user-{index:03d}",
                email=f"bulk{index}@example.com",
                nickname=f"批量用户{index}",
                created_at=moment(150 - index),
            )
            for index in range(25)
        ]
        session.add_all([admin, *users])
        await session.commit()
        for user in [admin, *users]:
            await session.refresh(user)
            session.add(
                TrainingPlan(
                    user_id=user.id,
                    week_start=day(20),
                    weekly_plan={"days": []},
                    difficulty_factor=1.0,
                    created_at=moment(20),
                )
            )
            session.add(
                WorkoutRecord(
                    user_id=user.id,
                    workout_date=day(1),
                    total_sets=4,
                    completed_sets=4,
                    completion_rate=1.0,
                    duration_minutes=30,
                    created_at=moment(1, hour=8),
                )
            )
        await session.commit()
        return admin


def _auth_headers(user_id: int) -> dict[str, str]:
    """Build bearer auth headers for a specific user id."""
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _items(response) -> list[dict]:
    return response.json()["items"]


def _ids(response) -> list[int]:
    return [item["id"] for item in _items(response)]


def _nicknames(response) -> set[str]:
    return {item["nickname"] for item in _items(response)}


# ── AC6: permissions ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_users_requires_authentication(client: AsyncClient, directory):
    """No bearer token means 401, never a partially filtered list."""
    response = await client.get("/api/admin/users")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_users_rejects_non_admin(client: AsyncClient, directory):
    """An authenticated non-admin gets 403."""
    response = await client.get(
        "/api/admin/users",
        headers=_auth_headers(directory["active"].id),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_filter_admins(client: AsyncClient, directory):
    """The is_admin filter must not become a side door for non-admins."""
    response = await client.get(
        "/api/admin/users?is_admin=true",
        headers=_auth_headers(directory["active"].id),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_gets_user_list(client: AsyncClient, directory):
    """An admin gets 200 with the paginated envelope."""
    response = await client.get(
        "/api/admin/users",
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"items", "total", "page", "page_size"}
    assert body["total"] == 8
    assert body["page"] == 1
    assert body["page_size"] == 20


@pytest.mark.asyncio
async def test_legacy_user_id_query_param_does_not_change_identity(
    client: AsyncClient, directory
):
    """Identity comes from the token only; the old user_id query param is inert."""
    response = await client.get(
        f"/api/admin/users?user_id={directory['active'].id}",
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 8


# ── AC6: minimization / masking ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_masks_contacts_and_hides_secrets(client: AsyncClient, directory):
    """Masked contacts go out; password hashes, ciphertext and raw contacts never do."""
    response = await client.get(
        "/api/admin/users",
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 200
    text = response.text
    for raw in (
        "wx-zhangsan-abcdef1234",
        "zhangsan@example.com",
        "argon2-hash-secret",
        "enc::zhangsan-ciphertext",
        "enc::admin-ciphertext",
    ):
        assert raw not in text
    for forbidden_field in ("password_hash", "llm_api_key", "encrypted_api_key"):
        assert forbidden_field not in text

    items = {item["id"]: item for item in _items(response)}
    active = items[directory["active"].id]
    assert active["email_masked"] == "z***@example.com"
    assert active["openid"].startswith("wx-zha")
    assert active["openid"].endswith("1234")
    assert "zhangsan" not in active["openid"]
    assert active["has_api_key"] is True
    assert active["llm_provider"] == "qwen"

    short = items[directory["api_key_missing"].id]
    assert short["openid"] == "****"
    assert short["has_api_key"] is False


# ── AC1: keyword search ────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_nickname"),
    [
        ("张三", "张三"),
        ("zhangsan@example.com", "张三"),
        ("ZHANGSAN@EXAMPLE.COM", "张三"),
        ("wx-lisi", "李四"),
        ("nokey", "没配Key"),
    ],
)
async def test_search_hits_nickname_email_and_openid(
    client: AsyncClient, directory, query, expected_nickname
):
    """Fuzzy keyword search matches nickname, email and openid."""
    response = await client.get(
        "/api/admin/users",
        params={"q": query},
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert expected_nickname in _nicknames(response)


@pytest.mark.asyncio
async def test_search_by_numeric_user_id_prefers_exact_match(client: AsyncClient, directory):
    """A numeric keyword exact-matches the user id and ranks that row first."""
    admin_id = directory["admin"].id

    response = await client.get(
        "/api/admin/users",
        params={"q": str(admin_id)},
        headers=_auth_headers(admin_id),
    )

    assert response.status_code == 200
    items = _items(response)
    assert items[0]["id"] == admin_id


@pytest.mark.asyncio
async def test_search_without_match_returns_empty_page(client: AsyncClient, directory):
    """No match is a 200 with an empty list and total 0."""
    response = await client.get(
        "/api/admin/users",
        params={"q": "definitely-not-a-user"},
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["%", "_", "'", '"', "\\", "' OR 1=1 --", "_%'\\"])
async def test_search_special_characters_are_not_wildcards(client: AsyncClient, directory, query):
    """LIKE metacharacters and quotes stay literal: no whole-table match, no 500."""
    response = await client.get(
        "/api/admin/users",
        params={"q": query},
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []


# ── AC2: combined filters ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filter_has_plan(client: AsyncClient, directory):
    """has_plan splits the directory by whether any plan row exists."""
    headers = _auth_headers(directory["admin"].id)

    with_plan = await client.get("/api/admin/users", params={"has_plan": "true"}, headers=headers)
    without_plan = await client.get(
        "/api/admin/users", params={"has_plan": "false"}, headers=headers
    )

    assert with_plan.status_code == 200
    assert without_plan.status_code == 200
    assert with_plan.json()["total"] == 6
    assert without_plan.json()["total"] == 2
    assert _nicknames(without_plan) == {"新用户", "李四"}


@pytest.mark.asyncio
async def test_filter_registered_range(client: AsyncClient, directory):
    """registered_from is inclusive and registered_to is exclusive (UTC instants)."""
    headers = _auth_headers(directory["admin"].id)

    after = await client.get(
        "/api/admin/users",
        params={"registered_from": "2026-05-16"},
        headers=headers,
    )
    before = await client.get(
        "/api/admin/users",
        params={"registered_to": "2026-05-16"},
        headers=headers,
    )

    assert after.json()["total"] == 4
    assert _nicknames(after) == {"没做分析", "没配Key", "新用户", "李四"}
    assert before.json()["total"] == 4
    assert _nicknames(before) == {"管理员", "张三", "有计划没打卡", "很久没来了"}


@pytest.mark.asyncio
async def test_filter_checkin_bounds(client: AsyncClient, directory):
    """checkins_min / checkins_max bound the accumulated check-in count."""
    headers = _auth_headers(directory["admin"].id)

    at_least_two = await client.get(
        "/api/admin/users", params={"checkins_min": 2}, headers=headers
    )
    at_most_one = await client.get(
        "/api/admin/users", params={"checkins_max": 1}, headers=headers
    )

    assert at_least_two.json()["total"] == 2
    assert _nicknames(at_least_two) == {"管理员", "张三"}
    assert at_most_one.json()["total"] == 6


@pytest.mark.asyncio
async def test_filter_active_within_days(client: AsyncClient, directory):
    """active_within_days keeps users whose last business event is recent enough."""
    response = await client.get(
        "/api/admin/users",
        params={"active_within_days": 7},
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 200
    assert _nicknames(response) == {"管理员", "张三", "没做分析", "没配Key", "李四"}


@pytest.mark.asyncio
async def test_filter_is_admin(client: AsyncClient, directory):
    """is_admin=true only returns the admin account."""
    response = await client.get(
        "/api/admin/users",
        params={"is_admin": "true"},
        headers=_auth_headers(directory["admin"].id),
    )

    assert _ids(response) == [directory["admin"].id]


@pytest.mark.asyncio
async def test_filter_has_api_key(client: AsyncClient, directory):
    """has_api_key splits accounts by whether they configured their own provider key."""
    headers = _auth_headers(directory["admin"].id)

    without_key = await client.get(
        "/api/admin/users", params={"has_api_key": "false"}, headers=headers
    )
    with_key = await client.get(
        "/api/admin/users", params={"has_api_key": "true"}, headers=headers
    )

    assert _nicknames(without_key) == {"新用户", "没配Key", "李四"}
    assert _nicknames(with_key) == {"管理员", "张三", "有计划没打卡", "很久没来了", "没做分析"}


@pytest.mark.asyncio
async def test_combined_filters_intersect(client: AsyncClient, directory):
    """Multiple filters combine with AND; total matches the unpaged row count."""
    headers = _auth_headers(directory["admin"].id)

    wide = await client.get(
        "/api/admin/users",
        params={
            "registered_from": "2026-05-01",
            "registered_to": "2026-06-01",
            "has_plan": "true",
            "checkins_min": 1,
            "active_within_days": 30,
            "page_size": 100,
        },
        headers=headers,
    )
    narrow = await client.get(
        "/api/admin/users",
        params={
            "registered_from": "2026-05-01",
            "registered_to": "2026-06-01",
            "has_plan": "true",
            "checkins_min": 2,
        },
        headers=headers,
    )

    assert wide.status_code == 200
    assert wide.json()["total"] == 2
    assert wide.json()["total"] == len(wide.json()["items"])
    assert _nicknames(wide) == {"管理员", "没配Key"}
    assert narrow.json()["total"] == 1
    assert _nicknames(narrow) == {"管理员"}


# ── AC3: sorting and pagination ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sort_registered_asc_and_desc(client: AsyncClient, directory):
    """Registration sort orders by created_at in both directions."""
    headers = _auth_headers(directory["admin"].id)

    ascending = await client.get(
        "/api/admin/users", params={"sort": "registered_asc", "page_size": 100}, headers=headers
    )
    descending = await client.get(
        "/api/admin/users", params={"sort": "registered_desc", "page_size": 100}, headers=headers
    )

    assert ascending.status_code == 200
    asc_times = [item["created_at"] for item in _items(ascending)]
    desc_times = [item["created_at"] for item in _items(descending)]
    assert asc_times == sorted(asc_times)
    assert desc_times == sorted(desc_times, reverse=True)
    assert _ids(ascending)[0] == directory["active"].id
    assert _ids(descending)[0] == directory["fresh"].id


@pytest.mark.asyncio
async def test_sort_last_active_asc_and_desc(client: AsyncClient, directory):
    """Last-activity sort orders by the derived activity timestamp in both directions."""
    headers = _auth_headers(directory["admin"].id)

    ascending = await client.get(
        "/api/admin/users", params={"sort": "last_active_asc", "page_size": 100}, headers=headers
    )
    descending = await client.get(
        "/api/admin/users", params={"sort": "last_active_desc", "page_size": 100}, headers=headers
    )

    assert ascending.status_code == 200
    asc_times = [item["last_active_at"] for item in _items(ascending)]
    desc_times = [item["last_active_at"] for item in _items(descending)]
    assert asc_times == sorted(asc_times)
    assert desc_times == sorted(desc_times, reverse=True)
    assert _ids(ascending)[0] == directory["inactive"].id
    assert _ids(descending)[0] == directory["fresh"].id


@pytest.mark.asyncio
async def test_invalid_sort_is_rejected(client: AsyncClient, directory):
    """sort is a fixed enum; unknown values are rejected."""
    response = await client.get(
        "/api/admin/users",
        params={"sort": "checkins_desc"},
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_pagination_last_page_and_out_of_range(client: AsyncClient, directory):
    """Page 3 holds the remainder; a page past the end is empty with the correct total."""
    headers = _auth_headers(directory["admin"].id)

    third = await client.get(
        "/api/admin/users", params={"page": 3, "page_size": 3}, headers=headers
    )
    beyond = await client.get(
        "/api/admin/users", params={"page": 99, "page_size": 3}, headers=headers
    )

    assert third.status_code == 200
    assert len(_items(third)) == 2
    assert third.json()["total"] == 8
    assert beyond.status_code == 200
    assert beyond.json()["items"] == []
    assert beyond.json()["total"] == 8
    assert beyond.json()["page"] == 99


@pytest.mark.asyncio
async def test_page_size_above_maximum_is_rejected(client: AsyncClient, directory):
    """An over-limit page_size is rejected with 422 rather than silently truncating."""
    response = await client.get(
        "/api/admin/users",
        params={"page_size": 101},
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_page_is_rejected(client: AsyncClient, directory):
    """page must be >= 1."""
    response = await client.get(
        "/api/admin/users",
        params={"page": 0},
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 422


# ── AC4: derived fields, one aggregate pass ───────────────────────────────────


@pytest.mark.asyncio
async def test_items_carry_derived_fields(client: AsyncClient, directory):
    """Every row carries plan/check-in/activity aggregates plus flags."""
    response = await client.get(
        "/api/admin/users",
        params={"page_size": 100},
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 200
    items = {item["id"]: item for item in _items(response)}
    active = items[directory["active"].id]
    assert active["has_plan"] is True
    assert active["plan_difficulty_factor"] == pytest.approx(1.25)
    assert active["total_checkins"] == 3
    assert active["checkins_30d"] == 2
    assert active["last_checkin_date"] == "2026-06-14"
    assert active["last_active_at"].startswith("2026-06-14T09:00:00")
    assert active["last_active_at"].endswith(("+00:00", "Z"))
    assert active["days_since_last_checkin"] == 1
    assert active["flags"] == []

    fresh = items[directory["fresh"].id]
    assert fresh["has_plan"] is False
    assert fresh["plan_difficulty_factor"] is None
    assert fresh["total_checkins"] == 0
    assert fresh["checkins_30d"] == 0
    assert fresh["last_checkin_date"] is None
    assert fresh["days_since_last_checkin"] is None
    assert fresh["last_active_at"].startswith("2026-06-14T12:00:00")

    inactive = items[directory["inactive"].id]
    assert inactive["last_checkin_date"] == "2026-05-26"
    assert inactive["days_since_last_checkin"] == 20


@pytest.mark.asyncio
async def test_derived_flags_follow_documented_rules(client: AsyncClient, directory):
    """Each flag appears exactly on the users whose data satisfies its rule."""
    response = await client.get(
        "/api/admin/users",
        params={"page_size": 100},
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 200
    flags = {item["id"]: set(item["flags"]) for item in _items(response)}
    assert flags[directory["admin"].id] == set()
    assert flags[directory["active"].id] == set()
    assert flags[directory["new_no_plan"].id] == {
        "new_no_plan",
        "never_analyzed",
        "api_key_missing",
    }
    assert flags[directory["planned"].id] == {"planned_no_checkin"}
    assert flags[directory["inactive"].id] == {"planned_no_checkin", "inactive_14d"}
    assert flags[directory["never_analyzed"].id] == {"never_analyzed"}
    assert flags[directory["api_key_missing"].id] == {"api_key_missing"}
    assert flags[directory["fresh"].id] == {"api_key_missing"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("new_no_plan", {"新用户"}),
        ("planned_no_checkin", {"有计划没打卡", "很久没来了"}),
        ("inactive_14d", {"很久没来了"}),
        ("never_analyzed", {"新用户", "没做分析"}),
        ("api_key_missing", {"新用户", "没配Key", "李四"}),
    ],
)
async def test_flag_filter_returns_only_flagged_users(
    client: AsyncClient, directory, flag, expected
):
    """Flag filtering returns exactly the accounts carrying that flag."""
    response = await client.get(
        "/api/admin/users",
        params={"flag": flag, "page_size": 100},
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 200
    assert _nicknames(response) == expected
    assert response.json()["total"] == len(expected)


@pytest.mark.asyncio
async def test_multiple_flags_are_union(client: AsyncClient, directory):
    """Repeated flag params return the union of the selected flags."""
    response = await client.get(
        "/api/admin/users",
        params=[("flag", "new_no_plan"), ("flag", "inactive_14d")],
        headers=_auth_headers(directory["admin"].id),
    )

    assert response.status_code == 200
    assert _nicknames(response) == {"新用户", "很久没来了"}


@pytest.mark.asyncio
async def test_query_count_does_not_grow_with_page_size(
    client: AsyncClient, engine, many_users
):
    """AC4: a 20-row page issues the same number of statements as a 1-row page."""
    statements: list[str] = []

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        headers = _auth_headers(many_users.id)
        single = await client.get("/api/admin/users", params={"page_size": 1}, headers=headers)
        single_count = len(statements)
        statements.clear()
        full = await client.get("/api/admin/users", params={"page_size": 20}, headers=headers)
        full_count = len(statements)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)

    assert single.status_code == 200
    assert full.status_code == 200
    assert len(single.json()["items"]) == 1
    assert len(full.json()["items"]) == 20
    assert single_count == full_count
    assert full_count <= 5
