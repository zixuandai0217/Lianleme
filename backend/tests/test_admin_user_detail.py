"""Admin user detail contract tests (ticket 37): sections, masking, timeline, 90-day windows.

These tests pin the external HTTP contract of ``GET /api/admin/users/{user_id}`` only:
which sections come back for which ``sections`` request, what each number means, masking
over the whole response text, timeline order / paging, the 90-day windows, and the
permission matrix. No SQL text or ORM internals are asserted.

Time bases are relative to a ``now`` captured when the fixture seeds data, so the suite
does not depend on a frozen wall clock; every boundary-sensitive fixture is placed at
least a day away from a window edge.
"""

import datetime as dt
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.adjustment import PlanAdjustment
from app.models.body_analysis import BodyAnalysisRecord
from app.models.chat_message import ChatMessageRecord
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.user import User
from app.models.weight import WeightRecord

# Canonical section order, also the order echoed back in ``sections``.
ALL_SECTIONS = (
    "profile",
    "body_analysis",
    "plan",
    "checkins",
    "weights",
    "timeline",
    "usage",
)

# Newest-first event sequence for the fully-populated fixture user.
RICH_TIMELINE = [
    "latest_chat",
    "latest_checkin",
    "latest_plan_adjustment",
    "latest_body_analysis",
    "latest_weight_record",
    "first_plan_generated",
    "first_body_analysis",
    "first_weight_record",
    "first_checkin",
    "registered",
]

FIRST_ANALYSIS = {
    "body_type": "ectomorph",
    "body_fat_range": "18-22%",
    "weak_muscles": ["胸", "肩"],
    "strengths": ["腿"],
    "muscle_scores": {"chest": 4},
    "summary": "偏瘦，先补胸背",
}

LATEST_ANALYSIS = {
    "body_type": "mesomorph",
    "body_fat_range": "15-18%",
    "weak_muscles": ["背"],
    "strengths": ["腿", "臀"],
    "muscle_scores": {"chest": 6},
    "summary": "有进步，保持节奏",
}

SIMPLE_WEEK = [
    {"day": 1, "focus": "腿", "exercises": [], "estimated_duration": 30, "is_rest_day": False}
]

ACTIVE_WEEK = [
    {
        "day": 1,
        "focus": "胸背",
        "exercises": [
            {
                "name": "卧推",
                "sets": 4,
                "reps": "8-12",
                "weight_suggestion": "体重 40%",
                "tips": "沉肩夹背",
                "rest_seconds": 90,
            },
            {
                "name": "划船",
                "sets": 3,
                "reps": "10-12",
                "weight_suggestion": "体重 35%",
                "tips": "先收肩胛",
                "rest_seconds": 60,
            },
        ],
        "estimated_duration": 55,
        "is_rest_day": False,
    },
    {"day": 2, "focus": "休息", "exercises": [], "estimated_duration": 0, "is_rest_day": True},
]


def moment(now: dt.datetime, days_ago: int, hour: int = 12) -> dt.datetime:
    """A fixed-clock instant ``days_ago`` days before the fixture's ``now``."""
    shifted = now - dt.timedelta(days=days_ago)
    return shifted.replace(hour=hour, minute=0, second=0, microsecond=0)


def hours_ago(now: dt.datetime, hours: int) -> dt.datetime:
    """A fixed-clock instant ``hours`` hours before the fixture's ``now``."""
    return now - dt.timedelta(hours=hours)


def day(today: dt.date, days_ago: int) -> dt.date:
    """A date ``days_ago`` days before the fixture's ``today``."""
    return today - dt.timedelta(days=days_ago)


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path):
    """Create an isolated SQLite database for the detail endpoint tests."""
    db_path = tmp_path / "admin-user-detail.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


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


@pytest_asyncio.fixture
async def directory(session_factory):
    """Seed an admin, a fully-populated user, and users whose data sources are missing.

    The rich user exercises every section; ``empty`` has only a registration row;
    ``legacy`` only a profile snapshot (no analysis history); ``no_adjust`` has a plan
    but never an adjustment. Data older than 90 days is seeded on purpose so the window
    is observable (check-in 100 days ago, weight 95 days ago).
    """
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()

    async with session_factory() as session:
        admin = User(
            openid="wx-detail-admin-0001",
            email="detail-admin@lianleme.test",
            nickname="管理员",
            is_admin=True,
            created_at=moment(now, 200, hour=9),
            llm_provider="openai",
            llm_api_key="enc::admin-detail-ciphertext",
        )
        rich = User(
            openid="wx-richuser-9f8e7d6c5b4a",
            email="rich.user@example.com",
            password_hash="argon2-detail-hash-secret",
            nickname="富数据用户",
            created_at=moment(now, 100, hour=9),
            profile={"goal": "增肌", "height_cm": 178},
            body_analysis=dict(LATEST_ANALYSIS),
            llm_provider="qwen",
            llm_api_key="enc::detail-ciphertext",
        )
        empty = User(
            openid="wx-empty-2109",
            email="empty@example.com",
            password_hash="argon2-empty-hash",
            nickname="空数据用户",
            created_at=moment(now, 10, hour=9),
        )
        legacy = User(
            openid="wx-legacy-snap-01",
            email="legacy@example.com",
            nickname="只有快照",
            created_at=moment(now, 40, hour=9),
            body_analysis={
                "body_type": "endomorph",
                "body_fat_range": "25-30%",
                "weak_muscles": ["腿"],
                "strengths": ["肩"],
                "summary": "先减脂再增肌",
            },
        )
        no_adjust = User(
            openid="wx-noadjust-0001",
            email="noadjust@example.com",
            nickname="有计划没调整",
            created_at=moment(now, 60, hour=9),
            llm_provider="openai",
            llm_api_key="enc::noadjust-ciphertext",
        )
        session.add_all([admin, rich, empty, legacy, no_adjust])
        await session.commit()
        for user in (admin, rich, empty, legacy, no_adjust):
            await session.refresh(user)

        # ── body analysis history (rich) ──────────────────────────────────────
        session.add_all(
            [
                BodyAnalysisRecord(
                    user_id=rich.id,
                    result=dict(FIRST_ANALYSIS),
                    created_at=moment(now, 90, hour=10),
                ),
                BodyAnalysisRecord(
                    user_id=rich.id,
                    result=dict(LATEST_ANALYSIS),
                    created_at=moment(now, 3, hour=11),
                ),
            ]
        )

        # ── plans: rich has an archived + an active plan, no_adjust one plan ──
        old_plan = TrainingPlan(
            user_id=rich.id,
            week_start=day(today, 80),
            weekly_plan=list(SIMPLE_WEEK),
            difficulty_factor=1.0,
            status="archived",
            created_at=moment(now, 80, hour=9),
        )
        active_plan = TrainingPlan(
            user_id=rich.id,
            week_start=day(today, 10),
            weekly_plan=[dict(item) for item in ACTIVE_WEEK],
            difficulty_factor=1.25,
            status="active",
            body_analysis_snapshot=dict(LATEST_ANALYSIS),
            profile_snapshot={"goal": "增肌"},
            analysis_captured_at=moment(now, 10, hour=9),
            created_at=moment(now, 10, hour=9),
        )
        unadjusted_plan = TrainingPlan(
            user_id=no_adjust.id,
            week_start=day(today, 60),
            weekly_plan=list(SIMPLE_WEEK),
            difficulty_factor=1.1,
            status="active",
            created_at=moment(now, 60, hour=9),
        )
        session.add_all([old_plan, active_plan, unadjusted_plan])
        await session.flush()

        adjustment = PlanAdjustment(
            id="adj_detail_00000000000001",
            user_id=rich.id,
            plan_id=active_plan.id,
            direction="decrease",
            reason="完成率 40%，下调下周难度",
            completion_rate=0.4,
            difficulty_rating=2.0,
            created_at=moment(now, 2, hour=10),
        )
        session.add(adjustment)
        await session.flush()
        active_plan.latest_adjustment_id = adjustment.id

        # ── check-ins: 100 days ago is outside the 90-day window ──────────────
        checkin_specs = [
            (day(today, 1), 1.0, 60),
            (day(today, 2), 0.9, 50),
            (day(today, 5), 0.5, 30),
            (day(today, 50), 0.3, 20),
            (day(today, 100), 0.7, 40),
        ]
        for index, (workout_date, rate, minutes) in enumerate(checkin_specs):
            session.add(
                WorkoutRecord(
                    user_id=rich.id,
                    workout_date=workout_date,
                    total_sets=10,
                    completed_sets=int(round(rate * 10)),
                    completion_rate=rate,
                    duration_minutes=minutes,
                    difficulty_rating=3,
                    created_at=moment(now, (today - workout_date).days, hour=15) + dt.timedelta(
                        seconds=index
                    ),
                )
            )

        # ── weights: 95 days ago is outside the 90-day window ────────────────
        weight_specs = [
            (day(today, 5), 72.5),
            (day(today, 30), 74.0),
            (day(today, 88), 76.0),
            (day(today, 95), 78.0),
        ]
        for recorded_date, weight in weight_specs:
            session.add(
                WeightRecord(
                    user_id=rich.id,
                    weight=weight,
                    recorded_date=recorded_date,
                    created_at=moment(now, (today - recorded_date).days, hour=8),
                )
            )

        # ── chat history (rich) ───────────────────────────────────────────────
        for offset, role in ((4, "user"), (3, "assistant"), (2, "user"), (1, "assistant")):
            session.add(
                ChatMessageRecord(
                    user_id=rich.id,
                    role=role,
                    content=f"yo coach {offset}",
                    created_at=hours_ago(now, offset),
                )
            )

        await session.commit()

    return {
        "admin": admin,
        "rich": rich,
        "empty": empty,
        "legacy": legacy,
        "no_adjust": no_adjust,
        "now": now,
        "today": today,
    }


def _auth_headers(user_id: int) -> dict[str, str]:
    """Build bearer auth headers for a specific user id."""
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def _detail(client: AsyncClient, admin_id: int, user_id: int, params=None):
    """Request one user's detail as the admin."""
    return await client.get(
        f"/api/admin/users/{user_id}",
        params=params or {},
        headers=_auth_headers(admin_id),
    )


def _stamp(value: str) -> dt.datetime:
    """Parse an ISO instant from the response (``Z`` suffix included)."""
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


# ── AC6: permissions ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detail_requires_authentication(client: AsyncClient, directory):
    """No bearer token means 401; the detail body never leaks without an identity."""
    response = await client.get(f"/api/admin/users/{directory['rich'].id}")

    assert response.status_code == 401
    assert "rich.user@example.com" not in response.text


@pytest.mark.asyncio
async def test_detail_rejects_non_admin(client: AsyncClient, directory):
    """An authenticated non-admin gets 403 for somebody else's detail."""
    response = await client.get(
        f"/api/admin/users/{directory['rich'].id}",
        headers=_auth_headers(directory["empty"].id),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_read_own_detail(client: AsyncClient, directory):
    """There is no impersonation bypass: a non-admin cannot read even their own detail."""
    response = await client.get(
        f"/api/admin/users/{directory['rich'].id}",
        headers=_auth_headers(directory["rich"].id),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_detail_returns_404_for_unknown_user(client: AsyncClient, directory):
    """An unknown user id is the only 404: everything else with data missing is 200."""
    response = await _detail(client, directory["admin"].id, 999_999)

    assert response.status_code == 404


# ── AC1: every section by default ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detail_returns_every_section_by_default(client: AsyncClient, directory):
    """Omitting ``sections`` returns all seven sections, in the canonical order."""
    response = await _detail(client, directory["admin"].id, directory["rich"].id)

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == directory["rich"].id
    assert body["sections"] == list(ALL_SECTIONS)
    assert set(body) == {"user_id", "sections", *ALL_SECTIONS}
    for section in ("profile", "body_analysis", "plan", "checkins", "weights", "usage"):
        assert body[section] is not None
    assert body["timeline"]["total"] == len(RICH_TIMELINE)


# ── AC1 / AC3: profile + masking ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_profile_section_is_the_masked_directory_row(client: AsyncClient, directory):
    """The profile carries identity, account state, key state and flags — all masked."""
    response = await _detail(
        client, directory["admin"].id, directory["rich"].id, {"sections": "profile"}
    )

    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["id"] == directory["rich"].id
    assert profile["nickname"] == "富数据用户"
    assert profile["is_admin"] is False
    assert profile["created_at"].startswith(
        moment(directory["now"], 100, hour=9).strftime("%Y-%m-%dT%H:%M:%S")
    )
    # openid: first 6 + last 4; email: first local character + domain.
    assert profile["openid"] == "wx-ric" + "*" * 14 + "5b4a"
    assert profile["email_masked"] == "r***@example.com"
    # Key state only: configured provider name, never the key itself.
    assert profile["has_api_key"] is True
    assert profile["llm_provider"] == "qwen"
    assert isinstance(profile["flags"], list)


@pytest.mark.asyncio
async def test_profile_flags_follow_the_directory_rules(client: AsyncClient, directory):
    """Attention flags are derived server-side with the same thresholds as the list."""
    response = await _detail(
        client, directory["admin"].id, directory["empty"].id, {"sections": "profile"}
    )

    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["has_api_key"] is False
    assert profile["llm_provider"] is None
    assert profile["flags"] == ["new_no_plan", "never_analyzed", "api_key_missing"]


@pytest.mark.asyncio
async def test_response_never_contains_raw_contacts_hashes_or_keys(client: AsyncClient, directory):
    """Whole-response masking: raw contacts, password hashes and ciphertext never appear."""
    response = await _detail(client, directory["admin"].id, directory["rich"].id)

    assert response.status_code == 200
    text = response.text
    for raw in (
        "wx-richuser-9f8e7d6c5b4a",  # full openid
        "rich.user@example.com",  # raw email
        "argon2-detail-hash-secret",  # password hash
        "enc::detail-ciphertext",  # encrypted API key
        "wx-detail-admin-0001",  # the requesting admin's own openid
        "detail-admin@lianleme.test",
        "enc::admin-detail-ciphertext",
    ):
        assert raw not in text
    for forbidden_field in ("password_hash", "llm_api_key", "encrypted_api_key"):
        assert forbidden_field not in text


# ── AC1: body analysis ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_body_analysis_section_uses_the_latest_record(client: AsyncClient, directory):
    """The latest analysis record wins and carries its own timestamp."""
    response = await _detail(
        client, directory["admin"].id, directory["rich"].id, {"sections": "body_analysis"}
    )

    assert response.status_code == 200
    analysis = response.json()["body_analysis"]
    assert analysis["body_type"] == "mesomorph"
    assert analysis["body_fat_range"] == "15-18%"
    assert analysis["weak_muscles"] == ["背"]
    assert analysis["strengths"] == ["腿", "臀"]
    assert analysis["summary"] == "有进步，保持节奏"
    assert analysis["source"] == "analysis_record"
    assert analysis["analyzed_at"].startswith(
        moment(directory["now"], 3, hour=11).strftime("%Y-%m-%dT%H:%M:%S")
    )


@pytest.mark.asyncio
async def test_body_analysis_falls_back_to_the_profile_snapshot(client: AsyncClient, directory):
    """Users analysed before the history table existed keep a readable summary."""
    response = await _detail(
        client, directory["admin"].id, directory["legacy"].id, {"sections": "body_analysis"}
    )

    assert response.status_code == 200
    analysis = response.json()["body_analysis"]
    assert analysis["body_type"] == "endomorph"
    assert analysis["source"] == "profile_snapshot"
    assert analysis["analyzed_at"] is None


# ── AC1: plan + latest adjustment ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_section_projects_plan_week_and_latest_adjustment(
    client: AsyncClient, directory
):
    """Current plan summary + the ticket-20 explanation projection (adjustment included)."""
    response = await _detail(
        client, directory["admin"].id, directory["rich"].id, {"sections": "plan"}
    )

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["difficulty_factor"] == 1.25
    assert plan["status"] == "active"
    assert plan["week_start"] == day(directory["today"], 10).isoformat()
    assert len(plan["week_structure"]) == 2

    training_day = plan["week_structure"][0]
    assert training_day["day"] == 1
    assert training_day["focus"] == "胸背"
    assert training_day["is_rest_day"] is False
    assert training_day["exercise_count"] == 2
    assert training_day["total_sets"] == 7
    assert training_day["estimated_duration"] == 55
    rest_day = plan["week_structure"][1]
    assert rest_day["is_rest_day"] is True
    assert rest_day["total_sets"] == 0

    assert plan["generation"]["body_type"] == "mesomorph"
    assert plan["generation"]["profile_goal"] == "增肌"

    adjustment = plan["latest_adjustment"]
    assert adjustment["direction"] == "decrease"
    assert adjustment["trigger"] == "completion_rate"
    assert adjustment["completion_rate"] == 0.4
    assert adjustment["reason"] == "完成率 40%，下调下周难度"
    assert adjustment["occurred_at"].startswith(
        moment(directory["now"], 2, hour=10).strftime("%Y-%m-%dT%H:%M:%S")
    )


@pytest.mark.asyncio
async def test_plan_section_without_adjustment_has_null_latest_adjustment(
    client: AsyncClient, directory
):
    """A plan that was never adjusted reports ``latest_adjustment: null`` (not a fake keep)."""
    response = await _detail(
        client, directory["admin"].id, directory["no_adjust"].id, {"sections": "plan"}
    )

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["difficulty_factor"] == 1.1
    assert plan["latest_adjustment"] is None


# ── AC5: check-ins agree with the user's own stats endpoint ───────────────────


@pytest.mark.asyncio
async def test_checkins_section_matches_the_user_stats_endpoint(client: AsyncClient, directory):
    """Streak, total and the 90-day series agree with ``/api/workout/{id}/stats``."""
    rich = directory["rich"]
    stats_response = await client.get(
        f"/api/workout/{rich.id}/stats", headers=_auth_headers(rich.id)
    )
    response = await _detail(
        client, directory["admin"].id, rich.id, {"sections": "checkins"}
    )

    assert stats_response.status_code == 200
    assert response.status_code == 200
    stats = stats_response.json()
    checkins = response.json()["checkins"]

    assert checkins["streak_days"] == stats["streak_days"]
    assert checkins["total_checkins"] == stats["total_checkins"] == 5
    assert checkins["window_days"] == 90

    series = checkins["series"]
    assert [point["workout_date"] for point in series] == [
        day(directory["today"], offset).isoformat() for offset in (1, 2, 5, 50)
    ]
    # Nothing older than the 90-day window leaks into the series.
    assert day(directory["today"], 100).isoformat() not in {
        point["workout_date"] for point in series
    }
    assert checkins["completion_rate_distribution"] == {"0-49": 1, "50-79": 1, "80-100": 2}


@pytest.mark.asyncio
async def test_checkins_series_carries_the_contract_fields(client: AsyncClient, directory):
    """Each point exposes date, completion rate, duration and the self-rated difficulty."""
    response = await _detail(
        client, directory["admin"].id, directory["rich"].id, {"sections": "checkins"}
    )

    point = response.json()["checkins"]["series"][0]
    assert set(point) >= {
        "workout_date",
        "completion_rate",
        "duration_minutes",
        "difficulty_rating",
    }
    assert point["completion_rate"] == 1.0
    assert point["duration_minutes"] == 60
    assert point["difficulty_rating"] == 3


# ── AC5: weights window + frequency ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_weights_section_series_and_frequency(client: AsyncClient, directory):
    """Only the last 90 days of weights are listed, with a recording frequency."""
    response = await _detail(
        client, directory["admin"].id, directory["rich"].id, {"sections": "weights"}
    )

    assert response.status_code == 200
    weights = response.json()["weights"]
    assert weights["window_days"] == 90
    assert [point["recorded_date"] for point in weights["series"]] == [
        day(directory["today"], offset).isoformat() for offset in (5, 30, 88)
    ]
    assert weights["record_count"] == 3
    assert weights["latest_weight"] == 72.5
    assert weights["last_recorded_date"] == day(directory["today"], 5).isoformat()
    # 3 records inside a 90-day window ≈ 0.23 records per week.
    assert weights["records_per_week"] == pytest.approx(0.23, abs=0.01)
    # The 95-day-old record stays outside the window.
    assert day(directory["today"], 95).isoformat() not in {
        point["recorded_date"] for point in weights["series"]
    }


# ── AC4: timeline ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeline_is_newest_first_with_fixed_event_types(client: AsyncClient, directory):
    """The derived timeline uses the fixed event vocabulary, newest first, no fabrications."""
    response = await _detail(
        client, directory["admin"].id, directory["rich"].id, {"sections": "timeline"}
    )

    assert response.status_code == 200
    timeline = response.json()["timeline"]
    assert timeline["total"] == len(RICH_TIMELINE)
    assert timeline["page"] == 1
    assert [event["type"] for event in timeline["items"]] == RICH_TIMELINE

    stamps = [_stamp(event["occurred_at"]) for event in timeline["items"]]
    assert stamps == sorted(stamps, reverse=True)
    for event in timeline["items"]:
        assert event["summary"]
        assert event["message"]


@pytest.mark.asyncio
async def test_timeline_pagination_and_out_of_range_page(client: AsyncClient, directory):
    """Timeline paging slices the derived events and keeps the true total."""
    page_two = await _detail(
        client,
        directory["admin"].id,
        directory["rich"].id,
        {"sections": "timeline", "page": 2, "page_size": 3},
    )
    page_last = await _detail(
        client,
        directory["admin"].id,
        directory["rich"].id,
        {"sections": "timeline", "page": 4, "page_size": 3},
    )
    page_beyond = await _detail(
        client,
        directory["admin"].id,
        directory["rich"].id,
        {"sections": "timeline", "page": 9, "page_size": 3},
    )

    assert page_two.status_code == 200
    body = page_two.json()["timeline"]
    assert [event["type"] for event in body["items"]] == RICH_TIMELINE[3:6]
    assert body["total"] == len(RICH_TIMELINE)
    assert body["page"] == 2
    assert body["page_size"] == 3

    assert [event["type"] for event in page_last.json()["timeline"]["items"]] == [
        RICH_TIMELINE[9]
    ]
    beyond = page_beyond.json()["timeline"]
    assert beyond["items"] == []
    assert beyond["total"] == len(RICH_TIMELINE)


@pytest.mark.asyncio
async def test_timeline_page_size_over_limit_is_rejected(client: AsyncClient, directory):
    """A page_size above the documented cap is a caller error (422), like the list."""
    response = await _detail(
        client,
        directory["admin"].id,
        directory["rich"].id,
        {"sections": "timeline", "page_size": 101},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_timeline_never_fabricates_events_for_missing_stages(
    client: AsyncClient, directory
):
    """A freshly registered user has exactly one event: the registration itself."""
    response = await _detail(
        client, directory["admin"].id, directory["empty"].id, {"sections": "timeline"}
    )

    assert response.status_code == 200
    timeline = response.json()["timeline"]
    assert timeline["total"] == 1
    assert [event["type"] for event in timeline["items"]] == ["registered"]
    assert timeline["items"][0]["occurred_at"].startswith(
        moment(directory["now"], 10, hour=9).strftime("%Y-%m-%dT%H:%M:%S")
    )


# ── AC1 / AC2: missing sources + section subsets ──────────────────────────────


@pytest.mark.asyncio
async def test_missing_data_sources_return_empty_sections_not_errors(
    client: AsyncClient, directory
):
    """A user without plan / analysis / weights still gets 200 with empty sections."""
    response = await _detail(client, directory["admin"].id, directory["empty"].id)

    assert response.status_code == 200
    body = response.json()
    assert body["sections"] == list(ALL_SECTIONS)
    assert body["profile"] is not None
    assert body["plan"] is None
    assert body["body_analysis"] is None
    assert body["checkins"]["series"] == []
    assert body["checkins"]["streak_days"] == 0
    assert body["checkins"]["total_checkins"] == 0
    assert body["checkins"]["completion_rate_distribution"] == {
        "0-49": 0,
        "50-79": 0,
        "80-100": 0,
    }
    assert body["weights"]["series"] == []
    assert body["weights"]["record_count"] == 0
    assert body["weights"]["records_per_week"] == 0
    assert body["weights"]["latest_weight"] is None
    assert body["timeline"]["total"] == 1
    assert body["usage"]["chat_message_count"] == 0
    assert body["usage"]["has_api_key"] is False


@pytest.mark.asyncio
async def test_sections_subset_returns_only_requested_keys_and_is_smaller(
    client: AsyncClient, directory
):
    """Requesting a subset returns only those sections and a materially smaller body."""
    full = await _detail(client, directory["admin"].id, directory["rich"].id)
    subset = await _detail(
        client, directory["admin"].id, directory["rich"].id, {"sections": "profile,usage"}
    )

    assert full.status_code == 200
    assert subset.status_code == 200
    subset_body = subset.json()
    assert subset_body["sections"] == ["profile", "usage"]
    assert set(subset_body) == {"user_id", "sections", "profile", "usage"}
    assert "timeline" not in subset_body
    assert "plan" not in subset_body
    assert len(subset.text) * 2 < len(full.text)


@pytest.mark.asyncio
async def test_sections_accepts_repeated_parameter_form(client: AsyncClient, directory):
    """``?sections=a&sections=b`` behaves exactly like the comma-joined form."""
    comma = await _detail(
        client, directory["admin"].id, directory["rich"].id, {"sections": "profile,weights"}
    )
    repeated = await _detail(
        client,
        directory["admin"].id,
        directory["rich"].id,
        [("sections", "weights"), ("sections", "profile")],
    )

    assert comma.status_code == 200
    assert repeated.status_code == 200
    assert comma.json() == repeated.json()


@pytest.mark.asyncio
async def test_unknown_section_is_rejected(client: AsyncClient, directory):
    """An unsupported section name is a caller error, not a silently ignored parameter."""
    response = await _detail(
        client, directory["admin"].id, directory["rich"].id, {"sections": "profile,warp"}
    )

    assert response.status_code == 422
    assert "warp" in response.text


@pytest.mark.asyncio
async def test_requested_but_empty_sections_are_present_as_null(client: AsyncClient, directory):
    """A requested section with no data is an explicit null, not a missing key."""
    response = await _detail(
        client,
        directory["admin"].id,
        directory["empty"].id,
        {"sections": "plan,body_analysis"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"user_id", "sections", "plan", "body_analysis"}
    assert body["plan"] is None
    assert body["body_analysis"] is None


# ── AC1: usage ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_usage_section_reports_key_status_and_conversation_counts(
    client: AsyncClient, directory
):
    """Usage exposes the AI key *state* plus aggregate chat counts (no message content)."""
    response = await _detail(
        client, directory["admin"].id, directory["rich"].id, {"sections": "usage"}
    )

    assert response.status_code == 200
    usage = response.json()["usage"]
    assert usage["has_api_key"] is True
    assert usage["llm_provider"] == "qwen"
    assert usage["chat_message_count"] == 4
    assert usage["user_message_count"] == 2
    assert usage["assistant_message_count"] == 2
    assert usage["last_chat_at"] is not None
    # Message bodies are not part of the usage section.
    assert "yo coach" not in response.text
