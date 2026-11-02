"""管理后台 CSV 导出：格式化、行数上限判定、审计写入与只读查询（工单 38）。

导出严格沿用列表的筛选与排序（复用 ``user_directory``），不带分页；行数超过上限时
直接拒绝而不是截断文件——「以为导出了全部、其实少了一半」比报错危险得多。每一次
经过鉴权的导出尝试（成功或被拒）都写一条审计记录，审计与文件通过同一个筛选摘要
短哈希对应起来，事后能回答「这个文件是谁、在什么条件下、什么时候导出的」。
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_export_audit import (
    OUTCOME_REJECTED,
    OUTCOME_SUCCESS,
    AdminExportAudit,
)
from app.services.admin import user_directory
from app.services.admin.user_directory import DirectoryFilters, as_utc

# UTF-8 BOM：Excel 打开中文表头与中文内容不乱码（解析器会自动跳过它）。
BOM = "\ufeff"

# 固定中文列序（产品契约，不随实现变化）。
EXPORT_HEADERS: tuple[str, ...] = (
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
)

CSV_MEDIA_TYPE = "text/csv; charset=utf-8"
FILENAME_PREFIX = "user-export"
FILENAME_DATE_FORMAT = "%Y%m%d"

YES = "是"
NO = "否"
KEY_NOT_CONFIGURED = "未配置"
KEY_CONFIGURED = "已配置"


@dataclass(frozen=True)
class ExportFile:
    """一次成功的导出：渲染好的文件与它的元信息。"""

    filename: str
    content: bytes
    row_count: int
    filter_summary: str
    filter_hash: str


@dataclass(frozen=True)
class ExportRejected:
    """一次被拒绝的导出：不产生文件，只产生审计与可读原因。"""

    message: str
    row_count: int
    limit: int
    filter_summary: str
    filter_hash: str


ExportResult = ExportFile | ExportRejected


def _text(value: Any) -> str:
    """Nulls become empty cells; everything else is its plain string form."""
    return "" if value is None else str(value)


def _yes_no(value: bool) -> str:
    """Booleans are rendered as the Chinese 是 / 否."""
    return YES if value else NO


def _iso_time(value: dt.datetime | None) -> str:
    """Aware UTC timestamps as ISO 8601 with offset; missing values stay empty."""
    return "" if value is None else as_utc(value).isoformat()


def _iso_date(value: dt.date | None) -> str:
    """Dates as ISO 8601 ``YYYY-MM-DD``; missing values stay empty."""
    return "" if value is None else value.isoformat()


def _number(value: float | None) -> str:
    """Numbers without thousands separators (1.25 -> ``1.25``, 1.0 -> ``1``)."""
    return "" if value is None else f"{float(value):g}"


def _key_status(row: dict[str, Any]) -> str:
    """Only the key *state* leaves the API: 未配置 or the configured provider name."""
    if not row["has_api_key"]:
        return KEY_NOT_CONFIGURED
    return row["llm_provider"] or KEY_CONFIGURED


def _csv_row(row: dict[str, Any]) -> list[str]:
    """One data row in the fixed column order (masking already happened upstream)."""
    return [
        str(row["id"]),
        _text(row["nickname"]),
        _text(row["email_masked"]),
        _text(row["openid"]),
        _iso_time(row["created_at"]),
        _yes_no(bool(row["is_admin"])),
        _yes_no(bool(row["has_plan"])),
        _number(row["plan_difficulty_factor"]),
        str(row["total_checkins"]),
        str(row["checkins_30d"]),
        _iso_date(row["last_checkin_date"]),
        _iso_time(row["last_active_at"]),
        _yes_no(bool(row["has_body_analysis"])),
        _key_status(row),
        ";".join(row["flags"]),
    ]


def render_csv(rows: Sequence[dict[str, Any]]) -> bytes:
    """Render the whole file: BOM + fixed header + one line per row (empty file if no rows)."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_HEADERS)
    for row in rows:
        writer.writerow(_csv_row(row))
    return (BOM + buffer.getvalue()).encode("utf-8")


def filename_for(exported_on: dt.date, filter_hash: str) -> str:
    """Download name: export date + short hash of the filter summary (ASCII, no encoding games)."""
    return f"{FILENAME_PREFIX}-{exported_on.strftime(FILENAME_DATE_FORMAT)}-{filter_hash}.csv"


def rejection_message(row_count: int, limit: int) -> str:
    """Readable over-limit message telling operations to narrow the filter."""
    return (
        f"筛选结果共 {row_count} 行，超过单次导出上限 {limit} 行，"
        "请收窄筛选条件后重试（不会导出被截断的文件）"
    )


async def _write_audit(
    db: AsyncSession,
    *,
    operator_id: int,
    filters: DirectoryFilters,
    row_count: int,
    outcome: str,
    now: dt.datetime,
    rejection_reason: str | None = None,
) -> None:
    """Append one audit row and commit it.

    The commit is deliberate: a rejected export raises a 4xx right after this call,
    and the request-scoped session rolls back on the way out — without an explicit
    commit the rejected-attempt audit would silently disappear.
    """
    db.add(
        AdminExportAudit(
            operator_id=operator_id,
            filter_summary=filters.summary_text(),
            filter_hash=filters.fingerprint(),
            row_count=row_count,
            outcome=outcome,
            rejection_reason=rejection_reason,
            created_at=now,
        )
    )
    await db.commit()


async def run_export(
    db: AsyncSession,
    *,
    operator_id: int,
    filters: DirectoryFilters,
    limit: int,
) -> ExportResult:
    """Run one export attempt: fetch + audit, then either a file or a rejection.

    Every authenticated attempt writes exactly one audit row, including the rejected one.
    """
    now = user_directory.utc_now()
    rows, total = await user_directory.export_users(db, filters, limit=limit)
    filter_hash = filters.fingerprint()
    filter_summary = filters.summary_text()

    if total > limit:
        message = rejection_message(total, limit)
        await _write_audit(
            db,
            operator_id=operator_id,
            filters=filters,
            row_count=total,
            outcome=OUTCOME_REJECTED,
            now=now,
            rejection_reason=message,
        )
        return ExportRejected(
            message=message,
            row_count=total,
            limit=limit,
            filter_summary=filter_summary,
            filter_hash=filter_hash,
        )

    content = render_csv(rows)
    await _write_audit(
        db,
        operator_id=operator_id,
        filters=filters,
        row_count=total,
        outcome=OUTCOME_SUCCESS,
        now=now,
        rejection_reason=None,
    )
    return ExportFile(
        filename=filename_for(now.date(), filter_hash),
        content=content,
        row_count=total,
        filter_summary=filter_summary,
        filter_hash=filter_hash,
    )


def _audit_payload(record: AdminExportAudit) -> dict[str, Any]:
    """Serialize one audit row for the read-only endpoint (times normalized to aware UTC)."""
    return {
        "id": record.id,
        "operator_id": record.operator_id,
        "filter_summary": record.filter_summary,
        "filter_hash": record.filter_hash,
        "row_count": record.row_count,
        "outcome": record.outcome,
        "rejection_reason": record.rejection_reason,
        "created_at": as_utc(record.created_at),
    }


async def list_audits(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """Read-only audit trail, newest first (append-only: the console never updates it)."""
    total = int((await db.execute(select(func.count(AdminExportAudit.id)))).scalar() or 0)
    query = (
        select(AdminExportAudit)
        .order_by(AdminExportAudit.created_at.desc(), AdminExportAudit.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    records = (await db.execute(query)).scalars().all()
    return [_audit_payload(record) for record in records], total
