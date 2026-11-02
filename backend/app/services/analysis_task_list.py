"""任务列表查询：状态投影、状态过滤与游标分页。

任务列表只读执行事实的摘要，绝不含结果明细或图片内容。对外状态与单任务轮询
接口共用同一条规则：数据库里仍为 pending/processing、但已过 ``expires_at`` 的
任务对外报告为 ``expired``（只读投影，不回写数据库）。因此 ``status=expired``
既匹配已落库的 expired 行，也匹配这些「实际已过期」的进行中行。

游标是 URL-safe base64 编码的紧凑 JSON（最后一行的时间戳 + 任务标识），按键集
分页读取，避免 offset 分页在并发写入时重复或丢项。
"""
from __future__ import annotations

import base64
import binascii
import datetime
import json
from typing import Iterable, Literal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis_task import AnalysisTask

TaskStatus = Literal["pending", "processing", "completed", "failed", "expired"]

# 终态一经写入不再改写；只有这两个状态会随时间对外变成 expired。
ACTIVE_STATUSES = frozenset({"pending", "processing"})
ERROR_CODE_INVALID_CURSOR = "invalid_cursor"
TASK_STATUSES: tuple[TaskStatus, ...] = (
    "pending",
    "processing",
    "completed",
    "failed",
    "expired",
)
DEFAULT_TASK_LIST_LIMIT = 20
MAX_TASK_LIST_LIMIT = 100
_MAX_CURSOR_LENGTH = 512


class InvalidCursor(ValueError):
    """游标无法解码，或结构/字段不满足约定。"""


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def as_utc(value: datetime.datetime | None) -> datetime.datetime | None:
    """SQLite 返回 naive datetime；统一成 UTC 以便比较与序列化。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def effective_status(task: AnalysisTask, now: datetime.datetime) -> str:
    """对外状态：进行中的任务超过过期时间即视为 expired（不写库）。"""
    if task.status in ACTIVE_STATUSES:
        expires_at = as_utc(task.expires_at)
        if expires_at is not None and expires_at <= now:
            return "expired"
    return task.status


def encode_cursor(task: AnalysisTask) -> str:
    created_at = as_utc(task.created_at)
    if created_at is None:
        raise ValueError("任务缺少创建时间，无法生成游标")
    payload = {"created_at": created_at.isoformat(), "task_id": task.task_id}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime.datetime, str]:
    """严格解码游标；任何可疑输入都收敛为 InvalidCursor（→ HTTP 422）。"""
    if not cursor or len(cursor) > _MAX_CURSOR_LENGTH:
        raise InvalidCursor("游标为空或过长")
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise InvalidCursor("游标无法解码") from None

    if not isinstance(payload, dict) or set(payload) != {"created_at", "task_id"}:
        raise InvalidCursor("游标结构不符合约定")
    created_at_raw = payload["created_at"]
    task_id = payload["task_id"]
    if not isinstance(created_at_raw, str) or not isinstance(task_id, str):
        raise InvalidCursor("游标字段类型不符合约定")
    if not task_id or len(task_id) > 64:
        raise InvalidCursor("游标中的任务标识无效")
    try:
        created_at = datetime.datetime.fromisoformat(created_at_raw)
    except ValueError:
        raise InvalidCursor("游标中的时间戳无效") from None
    if created_at.tzinfo is None:
        raise InvalidCursor("游标中的时间戳必须带时区")
    return created_at.astimezone(datetime.timezone.utc), task_id


def _status_filter(
    status: TaskStatus | None, now: datetime.datetime
) -> Iterable:
    """把对外五态翻译成数据库条件（含过期投影）。"""
    if status is None:
        return ()
    if status in ACTIVE_STATUSES:
        return (
            AnalysisTask.status == status,
            AnalysisTask.expires_at > now,
        )
    if status == "expired":
        return (
            or_(
                AnalysisTask.status == "expired",
                and_(
                    AnalysisTask.status.in_(ACTIVE_STATUSES),
                    AnalysisTask.expires_at <= now,
                ),
            ),
        )
    return (AnalysisTask.status == status,)


def _after_cursor(
    created_at: datetime.datetime, task_id: str
):
    """键集分页条件：严格按 (created_at desc, task_id desc) 取游标之后的行。

    ``created_at <= cursor`` 与 ``task_id < cursor`` 的组合在 Postgres 上等价于
    元组比较；在 SQLite 上（时间戳文本精度不同）也不会漏项或重复。
    """
    return or_(
        AnalysisTask.created_at < created_at,
        and_(
            AnalysisTask.created_at <= created_at,
            AnalysisTask.task_id < task_id,
        ),
    )


async def list_user_tasks(
    db: AsyncSession,
    *,
    user_id: int,
    status: TaskStatus | None = None,
    limit: int = DEFAULT_TASK_LIST_LIMIT,
    cursor: str | None = None,
) -> tuple[list[tuple[AnalysisTask, str]], str | None]:
    """返回 (任务, 对外状态) 列表与下一页游标；列表按创建时间倒序。

    只返回调用者自己的任务：归属由函数签名固定，调用方无法传入他人的标识。
    """
    now = utc_now()
    stmt = select(AnalysisTask).where(AnalysisTask.user_id == user_id)
    for condition in _status_filter(status, now):
        stmt = stmt.where(condition)
    if cursor is not None:
        cursor_created_at, cursor_task_id = decode_cursor(cursor)
        stmt = stmt.where(_after_cursor(cursor_created_at, cursor_task_id))
    stmt = (
        stmt.order_by(AnalysisTask.created_at.desc(), AnalysisTask.task_id.desc())
        .limit(limit + 1)
    )

    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = encode_cursor(items[-1]) if has_more and items else None
    return [(task, effective_status(task, now)) for task in items], next_cursor
