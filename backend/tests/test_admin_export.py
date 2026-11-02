"""Admin CSV export + export audit contract tests (ticket 38).

These tests pin the external HTTP contract only: response headers, the raw bytes of
the downloaded file (UTF-8 BOM), the parsed CSV content and column order, the row
limit behaviour, and the audit rows written for every authenticated export attempt.
No SQL text, ORM relationships or internal helper calls are asserted.
"""

import csv
import datetime as dt
import io
import re
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.body_analysis import BodyAnalysisRecord
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.user import User
from app.services.admin import user_directory

FIXED_NOW = dt.datetime(2026, 6, 15, 12, 0, tzinfo=dt.timezone.utc)
TODAY = FIXED_NOW.date()
EXPORT_DATE = "20260615"

# Fixed Chinese column order (contract, not an implementation detail).
EXPECTED_HEADER = [
    "用户 ID",
    "昵称",
    "邮箱",
    "openid",
    "注册时间",
    "是否管理员",
    "是否有训练计划",
    "计划难度系数",
    "累计打卡数",
    "近 30 天打卡数",
    "最近打卡日期",
    "最近活跃时间",
    "是否已做体型分析",
    "Key 状态",
    "需关注标记",
]

(
    COL_ID,
    COL_NICKNAME,
    COL_EMAIL,
    COL_OPENID,
    COL_CREATED_AT,
    COL_IS_ADMIN,
    COL_HAS_PLAN,
    COL_DIFFICULTY,
    COL_TOTAL_CHECKINS,
    COL_CHECKINS_30D,
    COL_LAST_CHECKIN_DATE,
    COL_LAST_ACTIVE_AT,
    COL_ANALYZED,
    COL_KEY_STATUS,
    COL_FLAGS,
) = range(len(EXPECTED_HEADER))

FILENAME_RE = re.compile(rf'^attachment; filename="user-export-{EXPORT_DATE}-[0-9a-f]{{8}}\.csv"$')


def moment(days_ago: int, hour: int = 12) -> dt.datetime:
    """Return a fixed-clock instant shifted back by ``days_ago`` days."""
    return (FIXED_NOW - dt.timedelta(days=days_ago)).replace(hour=hour)


def day(days_ago: int) -> dt.date:
    """Return the fixed-clock date shifted back by ``days_ago`` days."""
    return TODAY - dt.timedelta(days=days_ago)


@pytest_asyncio.fixture
async def engine_and_factory(tmp_path: Path):
    """Create an isolated SQLite database plus the engine used by the app."""
    db_path = tmp_path / "admin-export.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine, factory

    await engine.dispose()


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
    """Freeze the directory clock so the export date and flag thresholds are deterministic."""
    monkeypatch.setattr(user_directory, "utc_now", lambda: FIXED_NOW)


@pytest_asyncio.fixture
async def directory(session_factory):
    """Seed an admin plus users with plans / check-ins / analysis / keys and distinct flags."""
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
        fresh = User(
            openid="wx-lisi-xyz",
            email="lisi@example.com",
            nickname="李四",
            created_at=moment(1),
        )
        inactive = User(
            openid="wx-inactive-789",
            email="inactive@example.com",
            nickname="很久没来了",
            created_at=moment(90),
            llm_provider="openai",
            llm_api_key="enc::inactive-ciphertext",
        )
        planned = User(
            openid="uid-planned-01",
            email="planned@example.com",
            nickname="有计划没打卡",
            created_at=moment(60),
            llm_provider="openai",
            llm_api_key="enc::planned-ciphertext",
        )
        nokey = User(
            openid="uid9",
            email="nokey@example.com",
            nickname="没配Key",
            created_at=moment(25),
        )
        users = [admin, active, new_no_plan, fresh, inactive, planned, nokey]
        session.add_all(users)
        await session.commit()
        for user in users:
            await session.refresh(user)

        plan_specs = [
            (admin, 1.0, moment(38)),
            (active, 1.25, moment(10)),
            (inactive, 1.1, moment(80)),
            (planned, 1.5, moment(30)),
            (nokey, 1.05, moment(20)),
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
            (inactive, day(20), moment(20, hour=8)),
            (nokey, day(1), moment(1, hour=8)),
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
            (inactive, moment(70)),
            (planned, moment(20)),
            (nokey, moment(18)),
        ]
        for user, created_at in analysis_specs:
            session.add(
                BodyAnalysisRecord(
                    user_id=user.id,
                    result={"body_type": "mesomorph"},
                    created_at=created_at,
                )
            )

        await session.commit()
        return {
            "admin": admin,
            "active": active,
            "new_no_plan": new_no_plan,
            "fresh": fresh,
            "inactive": inactive,
            "planned": planned,
            "nokey": nokey,
        }


def _auth_headers(user_id: int) -> dict[str, str]:
    """Build bearer auth headers for a specific user id."""
    token = jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _csv_rows(response) -> list[list[str]]:
    """Decode a downloaded CSV file (BOM aware) into parsed rows including the header."""
    text = response.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text, newline="")))


def _rows_by_nickname(response) -> dict[str, list[str]]:
    """Index data rows (header excluded) by nickname for readable assertions."""
    rows = _csv_rows(response)
    return {row[COL_NICKNAME]: row for row in rows[1:]}


def _list_ids(response) -> list[int]:
    return [item["id"] for item in response.json()["items"]]


async def _export(client: AsyncClient, admin_id: int, params=None):
    """Request the CSV export with admin credentials."""
    return await client.get(
        "/api/admin/users/export",
        params=params or {},
        headers=_auth_headers(admin_id),
    )


async def _audits(client: AsyncClient, admin_id: int, params=None):
    """Read the export audit list with admin credentials."""
    return await client.get(
        "/api/admin/export-audits",
        params=params or {},
        headers=_auth_headers(admin_id),
    )


# ── AC6: permissions ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_requires_authentication(client: AsyncClient, directory):
    """No bearer token means 401 and no file is produced."""
    response = await client.get("/api/admin/users/export")

    assert response.status_code == 401
    assert "attachment" not in response.headers


@pytest.mark.asyncio
async def test_export_rejects_non_admin(client: AsyncClient, directory):
    """An authenticated non-admin gets 403 and no file is produced."""
    response = await _export(client, directory["active"].id)

    assert response.status_code == 403
    assert "attachment" not in response.headers


@pytest.mark.asyncio
async def test_admin_can_export(client: AsyncClient, directory):
    """An admin gets 200 with a CSV attachment."""
    response = await _export(client, directory["admin"].id)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")


@pytest.mark.asyncio
async def test_audit_list_requires_authentication(client: AsyncClient, directory):
    """The read-only audit endpoint is admin-only: no token -> 401."""
    response = await client.get("/api/admin/export-audits")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_audit_list_rejects_non_admin(client: AsyncClient, directory):
    """The read-only audit endpoint is admin-only: non-admin -> 403."""
    response = await _audits(client, directory["active"].id)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_audit_list_returns_rows_for_admin(client: AsyncClient, directory):
    """The read-only audit endpoint returns a paginated envelope to admins."""
    await _export(client, directory["admin"].id)

    response = await _audits(client, directory["admin"].id)

    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"items", "total", "page", "page_size"}
    assert body["total"] == 1
    assert body["page"] == 1


# ── AC1: download headers, filename, UTF-8 BOM ─────────────────────────────────


@pytest.mark.asyncio
async def test_export_sets_attachment_and_dated_hashed_filename(client: AsyncClient, directory):
    """The response is an attachment whose filename carries the export date and a filter hash."""
    response = await _export(client, directory["admin"].id)

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert FILENAME_RE.match(disposition), disposition
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_export_filename_hash_tracks_filters(client: AsyncClient, directory):
    """Same filters -> same short hash; different filters -> a different file name."""
    admin_id = directory["admin"].id

    first = await _export(client, admin_id, {"has_plan": "true"})
    same = await _export(client, admin_id, {"has_plan": "true"})
    other = await _export(client, admin_id, {"has_plan": "false"})

    assert first.status_code == 200
    assert (
        first.headers["content-disposition"] == same.headers["content-disposition"]
    )
    assert first.headers["content-disposition"] != other.headers["content-disposition"]


@pytest.mark.asyncio
async def test_export_starts_with_utf8_bom(client: AsyncClient, directory):
    """The raw bytes start with the UTF-8 BOM so Excel opens Chinese headers correctly."""
    response = await _export(client, directory["admin"].id)

    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert response.text.startswith("\ufeff")
    # Decoding after the BOM must be plain valid UTF-8.
    assert "用户 ID" in response.content[3:].decode("utf-8")


# ── AC2: header order and cell formatting ──────────────────────────────────────


@pytest.mark.asyncio
async def test_export_header_is_fixed_chinese_column_order(client: AsyncClient, directory):
    """The first row is exactly the documented Chinese header, in order, 15 columns wide."""
    response = await _export(client, directory["admin"].id)

    header = _csv_rows(response)[0]
    assert header == EXPECTED_HEADER
    assert len(header) == 15


@pytest.mark.asyncio
async def test_export_formats_times_booleans_and_nulls(client: AsyncClient, directory):
    """Times are ISO 8601 with offset, booleans are 是/否, nulls are empty strings."""
    response = await _export(client, directory["admin"].id)
    rows = _rows_by_nickname(response)

    active = rows["张三"]
    assert active[COL_ID] == str(directory["active"].id)
    assert active[COL_CREATED_AT] == "2026-03-07T12:00:00+00:00"
    assert active[COL_IS_ADMIN] == "否"
    assert active[COL_HAS_PLAN] == "是"
    assert active[COL_DIFFICULTY] == "1.25"
    assert active[COL_TOTAL_CHECKINS] == "3"
    assert active[COL_CHECKINS_30D] == "2"
    assert active[COL_LAST_CHECKIN_DATE] == "2026-06-14"
    assert active[COL_LAST_ACTIVE_AT] == "2026-06-14T08:00:00+00:00"
    assert active[COL_ANALYZED] == "是"
    assert active[COL_KEY_STATUS] == "qwen"
    assert active[COL_FLAGS] == ""

    admin_row = rows["管理员"]
    assert admin_row[COL_IS_ADMIN] == "是"
    assert admin_row[COL_KEY_STATUS] == "openai"

    fresh = rows["李四"]
    assert fresh[COL_HAS_PLAN] == "否"
    assert fresh[COL_DIFFICULTY] == ""
    assert fresh[COL_TOTAL_CHECKINS] == "0"
    assert fresh[COL_CHECKINS_30D] == "0"
    assert fresh[COL_LAST_CHECKIN_DATE] == ""
    assert fresh[COL_ANALYZED] == "否"
    assert fresh[COL_KEY_STATUS] == "未配置"
    assert fresh[COL_CREATED_AT] == "2026-06-14T12:00:00+00:00"

    assert rows["新用户"][COL_FLAGS] == "new_no_plan;never_analyzed;api_key_missing"
    assert rows["很久没来了"][COL_FLAGS] == "planned_no_checkin;inactive_14d"


@pytest.mark.asyncio
async def test_export_masks_contacts_and_omits_secrets(client: AsyncClient, directory):
    """openid / email are masked and no password hash or encrypted key reaches the file."""
    response = await _export(client, directory["admin"].id)
    rows = _rows_by_nickname(response)
    text = response.content.decode("utf-8-sig")

    active = rows["张三"]
    assert active[COL_EMAIL] == "z***@example.com"
    assert active[COL_OPENID] == "wx-zha" + "*" * 12 + "1234"
    assert rows["没配Key"][COL_OPENID] == "****"

    for leaked in (
        "wx-zhangsan-abcdef1234",
        "zhangsan@example.com",
        "argon2-hash-secret",
        "enc::zhangsan-ciphertext",
        "enc::admin-ciphertext",
        "llm_api_key",
        "password_hash",
    ):
        assert leaked not in text


# ── AC3: rows follow the list's filters, sort and total ────────────────────────


@pytest.mark.asyncio
async def test_export_row_count_matches_list_total(client: AsyncClient, directory):
    """Row count equals the same filter's list total; the default sort matches the list."""
    admin_id = directory["admin"].id

    listing = await client.get(
        "/api/admin/users", params={"page_size": 100}, headers=_auth_headers(admin_id)
    )
    response = await _export(client, admin_id)

    assert listing.status_code == 200
    assert response.status_code == 200
    rows = _csv_rows(response)[1:]
    assert len(rows) == listing.json()["total"] == 7
    assert [int(row[COL_ID]) for row in rows] == _list_ids(listing)


@pytest.mark.asyncio
async def test_export_reuses_list_sort_and_filters(client: AsyncClient, directory):
    """Two different filter/sort combinations produce rows matching the list's ids."""
    admin_id = directory["admin"].id
    headers = _auth_headers(admin_id)

    for params in (
        {"sort": "last_active_asc", "has_plan": "true"},
        {"sort": "registered_asc", "flag": "api_key_missing"},
    ):
        listing = await client.get(
            "/api/admin/users", params={**params, "page_size": 100}, headers=headers
        )
        response = await _export(client, admin_id, params)

        assert listing.status_code == 200
        assert response.status_code == 200
        rows = _csv_rows(response)[1:]
        assert len(rows) == listing.json()["total"]
        assert [int(row[COL_ID]) for row in rows] == _list_ids(listing)


@pytest.mark.asyncio
async def test_export_content_follows_the_filter(client: AsyncClient, directory):
    """Changing the filter changes both the row count and the exported rows."""
    admin_id = directory["admin"].id

    with_plan = await _export(client, admin_id, {"has_plan": "true"})
    without_plan = await _export(client, admin_id, {"has_plan": "false"})

    assert with_plan.status_code == 200
    assert without_plan.status_code == 200
    assert len(_csv_rows(with_plan)[1:]) == 5
    assert set(_rows_by_nickname(with_plan)) == {
        "管理员",
        "张三",
        "很久没来了",
        "有计划没打卡",
        "没配Key",
    }
    assert len(_csv_rows(without_plan)[1:]) == 2
    assert set(_rows_by_nickname(without_plan)) == {"新用户", "李四"}


@pytest.mark.asyncio
async def test_export_has_no_pagination(client: AsyncClient, directory, session_factory):
    """The export is not capped by the list page size: everything matching is written."""
    async with session_factory() as session:
        for index in range(25):
            session.add(
                User(
                    openid=f"wx-bulk-{index:03d}",
                    email=f"bulk{index}@example.com",
                    nickname=f"批量用户{index}",
                    created_at=moment(50 + index),
                )
            )
        await session.commit()

    admin_id = directory["admin"].id
    listing = await client.get(
        "/api/admin/users", params={"page_size": 100}, headers=_auth_headers(admin_id)
    )
    response = await _export(client, admin_id)

    assert listing.json()["total"] == 32
    assert len(_csv_rows(response)[1:]) == 32


# ── AC4: zero rows and the row limit ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_zero_rows_returns_header_only_file(client: AsyncClient, directory):
    """An empty filter result is a 200 file that contains the header row only."""
    response = await _export(client, directory["admin"].id, {"q": "definitely-not-a-user"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = _csv_rows(response)
    assert rows == [EXPECTED_HEADER]
    assert response.content.startswith(b"\xef\xbb\xbf")


@pytest.mark.asyncio
async def test_over_limit_is_rejected_with_narrow_hint(
    client: AsyncClient, directory, monkeypatch
):
    """Over the row limit the request fails with a readable 收窄筛选 message, not a cut file."""
    monkeypatch.setattr(settings, "ADMIN_EXPORT_ROW_LIMIT", 3)

    response = await _export(client, directory["admin"].id)

    assert response.status_code == 400
    assert "attachment" not in response.headers
    detail = response.json()["detail"]
    assert detail["code"] == "export_row_limit_exceeded"
    assert "收窄" in detail["message"]
    assert "3" in detail["message"]


# ── AC5: audit records for every attempt ───────────────────────────────────────


@pytest.mark.asyncio
async def test_success_export_writes_audit_record(client: AsyncClient, directory):
    """A successful export leaves one audit row: operator, filters, rows, time, no reason."""
    admin_id = directory["admin"].id

    export = await _export(client, admin_id, {"q": "张三", "sort": "registered_asc"})
    audits = await _audits(client, admin_id)

    assert export.status_code == 200
    assert len(_csv_rows(export)) == 2
    assert audits.status_code == 200
    items = audits.json()["items"]
    assert len(items) == 1
    record = items[0]
    assert record["operator_id"] == admin_id
    assert record["outcome"] == "success"
    assert record["row_count"] == 1
    assert record["rejection_reason"] is None
    assert "q=张三" in record["filter_summary"]
    assert "sort=registered_asc" in record["filter_summary"]
    assert re.search(r"[0-9a-f]{8}", record["filter_hash"])
    assert record["created_at"].startswith("2026-06-15T12:00:00")
    # The audit row is attributed to the filter hash used in the file name.
    assert record["filter_hash"] in export.headers["content-disposition"]


@pytest.mark.asyncio
async def test_rejected_export_writes_audit_record_with_reason(
    client: AsyncClient, directory, monkeypatch
):
    """A rejected export still writes an audit row carrying the rejection reason."""
    monkeypatch.setattr(settings, "ADMIN_EXPORT_ROW_LIMIT", 3)
    admin_id = directory["admin"].id

    rejected = await _export(client, admin_id, {"has_plan": "true"})
    audits = await _audits(client, admin_id)

    assert rejected.status_code == 400
    items = audits.json()["items"]
    assert len(items) == 1
    record = items[0]
    assert record["operator_id"] == admin_id
    assert record["outcome"] == "rejected"
    assert record["row_count"] == 5
    assert "收窄" in record["rejection_reason"]
    assert "has_plan=True" in record["filter_summary"]


@pytest.mark.asyncio
async def test_every_attempt_writes_one_audit_row(client: AsyncClient, directory):
    """Each attempt appends a row; the list is newest first and paginates."""
    admin_id = directory["admin"].id

    await _export(client, admin_id, {"has_plan": "false"})
    await _export(client, admin_id)

    first_page = await _audits(client, admin_id)
    second_page = await _audits(client, admin_id, {"page": 2, "page_size": 1})

    body = first_page.json()
    assert body["total"] == 2
    assert [item["row_count"] for item in body["items"]] == [7, 2]
    assert second_page.status_code == 200
    assert second_page.json()["total"] == 2
    assert len(second_page.json()["items"]) == 1


@pytest.mark.asyncio
async def test_denied_attempts_do_not_write_audit_rows(client: AsyncClient, directory):
    """401/403 attempts never reach the handler, so they cannot be attributed to an operator."""
    await client.get("/api/admin/users/export")
    await _export(client, directory["active"].id)

    audits = await _audits(client, directory["admin"].id)

    assert audits.status_code == 200
    assert audits.json()["total"] == 0
