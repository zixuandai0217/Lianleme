"""Web Push 重通道：订阅服务、发送器、作业执行器与常驻 worker（工单 35）。

边界与提醒 tick 一致：
- tick 只把「已写好的站内投递」复制成一条 ``web_push`` 待投递记录，并投递一条
  ``push_jobs`` 作业；tick 内不发生任何外部网络调用。
- 真正的发送、超时与重试由 ``PushJobExecutor`` 完成；``PushJobWorker`` 只是它的
  进程内周期宿主（单实例部署，先睡再跑，异常不杀循环）。
- 发送器是阻塞的 pywebpush，因此在线程里调用；测试用替身实现同一 ``PushSender``
  协议，不访问真实推送服务。

日志只允许出现订阅 id 或 endpoint 指纹，绝不记录 endpoint 原文、密钥材料或通知正文。
"""

import asyncio
import datetime
import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pywebpush import WebPushException, webpush
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import (
    EVENT_PUSH_JOB_ENQUEUE_FAILED,
    EVENT_PUSH_JOB_ENQUEUED,
    EVENT_PUSH_SEND_FAILED,
    EVENT_PUSH_SEND_INVALID,
    EVENT_PUSH_SEND_RETRYABLE,
    EVENT_PUSH_SEND_SENT,
    EVENT_PUSH_WORKER_FAILED,
    FIELD_ATTEMPTS,
    FIELD_CHANNEL,
    FIELD_DELIVERY_ID,
    FIELD_ENDPOINT_HASH,
    FIELD_ERROR_CLASS,
    FIELD_ERROR_CODE,
    FIELD_JOB_ID,
    FIELD_OUTCOME,
    FIELD_SUBSCRIPTION_ID,
    FIELD_USER_ID,
    log_event,
)
from app.models.push import (
    PUSH_JOB_STATUS_FAILED,
    PUSH_JOB_STATUS_PENDING,
    PUSH_JOB_STATUS_SENT,
    SUBSCRIPTION_FAILURE_ENDPOINT_GONE,
    PushJob,
    PushSubscription,
)
from app.models.reminder import (
    CHANNEL_WEB_PUSH,
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_PENDING,
    DELIVERY_STATUS_SENT,
    ReminderDelivery,
)

logger = logging.getLogger(__name__)

# 稳定的对外错误码：服务端未配置推送密钥时，订阅登记被拒绝。
ERROR_CODE_PUSH_UNAVAILABLE = "push_unavailable"
# 同一 endpoint 已被另一个账号登记：拒绝而不是静默转移归属。
ERROR_CODE_PUSH_ENDPOINT_IN_USE = "push_endpoint_in_use"


class PushEndpointInUse(RuntimeError):
    """该 endpoint 已归属另一个账号，拒绝静默转移。"""

# 发送结果三分类：成功 / 永久失效 / 可重试。
SEND_OUTCOME_SENT = "sent"
SEND_OUTCOME_INVALID = "invalid"
SEND_OUTCOME_RETRYABLE = "retryable"
# 执行器内部失败（订阅被删、投递记录缺失、执行前已注销），不经过发送器。
SEND_OUTCOME_FAILED = "failed"

# 推送服务明确表示「订阅已不存在」的 HTTP 状态：404 / 410。
INVALID_SUBSCRIPTION_STATUS_CODES = frozenset({404, 410})

# 发送失败原因里允许落库的安全摘要（不包含推送服务返回原文）。
ERROR_SUBSCRIPTION_MISSING = "subscription_missing"
ERROR_SUBSCRIPTION_INACTIVE = "subscription_inactive"
ERROR_DELIVERY_MISSING = "delivery_missing"
ERROR_SUBSCRIPTION_OWNER_MISMATCH = "subscription_owner_mismatch"


@dataclass(frozen=True)
class PushSendResult:
    """一次发送尝试的分类结果；``detail`` 只放安全摘要。"""

    outcome: str
    detail: str | None = None


@dataclass(frozen=True)
class PushTarget:
    """发送器需要的最小订阅快照（与 ORM 解耦，便于在线程里使用）。"""

    subscription_id: int
    endpoint: str
    p256dh: str
    auth: str


class PushSender(Protocol):
    """发送器协议：生产实现是 pywebpush，测试实现记录调用。"""

    def send(self, subscription: PushTarget, payload: dict) -> PushSendResult:
        """同步发送（调用方负责放进线程）。"""


def endpoint_fingerprint(endpoint: str) -> str:
    """endpoint 的稳定指纹，用于日志关联而不泄漏订阅原文。"""
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:12]


class WebPushSender:
    """生产发送器：用配置的 VAPID 密钥调用 pywebpush（阻塞，调用方放线程）。"""

    def __init__(
        self,
        private_key: str | None = None,
        subject: str | None = None,
        timeout_seconds: float | None = None,
    ):
        self._private_key = settings.VAPID_PRIVATE_KEY if private_key is None else private_key
        self._subject = settings.VAPID_SUBJECT if subject is None else subject
        self._timeout_seconds = (
            settings.PUSH_SEND_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )

    def send(self, subscription: PushTarget, payload: dict) -> PushSendResult:
        subscription_info = {
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=self._private_key,
                vapid_claims={"sub": self._subject},
                timeout=self._timeout_seconds,
            )
        except WebPushException as exc:
            status_code = exc.status_code
            detail = f"http_{status_code}" if status_code is not None else "push_service_error"
            outcome = (
                SEND_OUTCOME_INVALID
                if status_code in INVALID_SUBSCRIPTION_STATUS_CODES
                else SEND_OUTCOME_RETRYABLE
            )
            return PushSendResult(outcome, detail)
        except Exception as exc:  # 网络/证书等瞬时异常：可重试，不把原文写进库。
            return PushSendResult(SEND_OUTCOME_RETRYABLE, type(exc).__name__)
        return PushSendResult(SEND_OUTCOME_SENT)


class PushService:
    """订阅登记、注销与状态查询（全部以令牌身份为准）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @property
    def available(self) -> bool:
        """通道是否可用：三项 VAPID 配置齐全才为真。"""
        return settings.web_push_available()

    async def active_subscription_count(self, user_id: int) -> int:
        count = (
            await self.db.execute(
                select(func.count())
                .select_from(PushSubscription)
                .where(
                    PushSubscription.user_id == user_id,
                    PushSubscription.is_active.is_(True),
                )
            )
        ).scalar() or 0
        return int(count)

    async def subscribe(
        self,
        user_id: int,
        *,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> PushSubscription:
        """按 endpoint upsert：已存在则更新密钥并重新激活，不会产生第二行。"""
        existing = (
            await self.db.execute(
                select(PushSubscription).where(PushSubscription.endpoint == endpoint)
            )
        ).scalar_one_or_none()

        if existing is None:
            row = PushSubscription(
                user_id=user_id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                is_active=True,
            )
            try:
                async with self.db.begin_nested():
                    self.db.add(row)
                    await self.db.flush()
            except IntegrityError:
                # 并发登记同一 endpoint：唯一索引只允许一行，读回后走更新路径。
                row = (
                    await self.db.execute(
                        select(PushSubscription).where(
                            PushSubscription.endpoint == endpoint
                        )
                    )
                ).scalar_one()
        else:
            row = existing

        if row.user_id != user_id:
            # 同一浏览器换了账号：不静默转移归属，要求先在原账号注销或换一台设备。
            raise PushEndpointInUse()
        # 同一账号重新登记：更新密钥并重新激活。
        row.p256dh = p256dh
        row.auth = auth
        row.is_active = True
        row.failure_reason = None
        await self.db.flush()
        return row

    async def deactivate_all(self, user_id: int) -> int:
        """注销本人的全部订阅：软失效，保留行以便审计与重新登记。"""
        rows = (
            (
                await self.db.execute(
                    select(PushSubscription).where(
                        PushSubscription.user_id == user_id,
                        PushSubscription.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.is_active = False
        if rows:
            await self.db.flush()
        return len(rows)


async def enqueue_web_push_delivery(
    db: AsyncSession,
    *,
    user_id: int,
    rule_code: str,
    local_date: datetime.date,
    subscription_id: int,
    payload: dict,
) -> bool:
    """在 tick 事务内写一条待投递 web_push 记录和一条唯一作业。

    调用方已在 tick 内完成「通道可用 + 用户有有效订阅」的判定；这里只负责落库。
    唯一键冲突即视为幂等命中（返回 False），异常只记事件、不打断本次 tick 的
    站内投递——推送是增强通道，不能反过来影响轻通道。
    """
    delivery = ReminderDelivery(
        user_id=user_id,
        rule_code=rule_code,
        local_date=local_date,
        channel=CHANNEL_WEB_PUSH,
        status=DELIVERY_STATUS_PENDING,
        payload=payload,
    )
    try:
        async with db.begin_nested():
            db.add(delivery)
            await db.flush()
    except IntegrityError:
        return False
    except Exception as exc:
        log_event(
            logger,
            EVENT_PUSH_JOB_ENQUEUE_FAILED,
            message="Web Push 投递记录写入失败",
            level=logging.WARNING,
            **{
                FIELD_USER_ID: user_id,
                FIELD_ERROR_CLASS: type(exc).__name__,
            },
        )
        return False

    job = PushJob(
        delivery_id=delivery.id,
        user_id=user_id,
        subscription_id=subscription_id,
        status=PUSH_JOB_STATUS_PENDING,
        attempts=0,
    )
    try:
        async with db.begin_nested():
            db.add(job)
            await db.flush()
    except IntegrityError:
        # 作业侧唯一键已存在：记录与作业必须成对，视为幂等命中。
        return False
    except Exception as exc:
        log_event(
            logger,
            EVENT_PUSH_JOB_ENQUEUE_FAILED,
            message="Web Push 作业写入失败",
            level=logging.WARNING,
            **{
                FIELD_USER_ID: user_id,
                FIELD_DELIVERY_ID: delivery.id,
                FIELD_ERROR_CLASS: type(exc).__name__,
            },
        )
        return False

    log_event(
        logger,
        EVENT_PUSH_JOB_ENQUEUED,
        message="Web Push 作业已投递",
        **{
            FIELD_USER_ID: user_id,
            FIELD_DELIVERY_ID: delivery.id,
            FIELD_JOB_ID: job.id,
            FIELD_SUBSCRIPTION_ID: subscription_id,
            FIELD_CHANNEL: CHANNEL_WEB_PUSH,
        },
    )
    return True


@dataclass(frozen=True)
class _DeliveryPayload:
    """发送载荷：只允许通知标题/正文/跳转目标，绝不带订阅密钥。"""

    title: str
    body: str
    target_path: str

    def as_dict(self) -> dict:
        return {"title": self.title, "body": self.body, "target_path": self.target_path}


@dataclass(frozen=True)
class _JobSnapshot:
    """执行器读取阶段物化的最小事实，发送期间不持有数据库事务。"""

    job_id: int
    delivery_id: int
    subscription_id: int
    attempts: int
    payload: _DeliveryPayload | None
    target: PushTarget | None
    subscription_active: bool
    error: str | None = None


class PushJobExecutor:
    """消费 ``push_jobs``：读取批次 → 线程内发送 → 短事务回写状态。

    执行器用条件 UPDATE 抢租约（``claimed_at``），发送前释放会话与事务；
    崩溃遗留的旧租约在下一轮被回收，多实例下同一作业最多被一个执行者拿到。
    """

    def __init__(
        self,
        sender: PushSender,
        session_factory: Callable = AsyncSessionLocal,
        max_attempts: int | None = None,
        batch_size: int | None = None,
    ):
        self._sender = sender
        self._session_factory = session_factory
        self.max_attempts = (
            settings.PUSH_JOB_MAX_ATTEMPTS if max_attempts is None else max_attempts
        )
        self.batch_size = (
            settings.PUSH_JOB_BATCH_SIZE if batch_size is None else batch_size
        )
        # 发送超时既用于线程内的调用，也用于判定旧租约是否已失效。
        self._timeout_seconds = settings.PUSH_SEND_TIMEOUT_SECONDS

    async def run_once(self) -> dict:
        """执行一批待处理作业；返回本次可观察摘要。"""
        snapshots = await self._load_batch()
        summary = {
            "claimed": len(snapshots),
            "sent": 0,
            "failed": 0,
            "retried": 0,
        }
        if not snapshots:
            return summary

        results: list[tuple[_JobSnapshot, PushSendResult, int]] = []
        for snapshot in snapshots:
            if snapshot.error is not None:
                results.append(
                    (
                        snapshot,
                        PushSendResult(SEND_OUTCOME_FAILED, snapshot.error),
                        snapshot.attempts,
                    )
                )
                continue
            if snapshot.target is None:
                results.append(
                    (
                        snapshot,
                        PushSendResult(SEND_OUTCOME_FAILED, ERROR_SUBSCRIPTION_MISSING),
                        snapshot.attempts,
                    )
                )
                continue
            if not snapshot.subscription_active:
                results.append(
                    (
                        snapshot,
                        PushSendResult(SEND_OUTCOME_FAILED, ERROR_SUBSCRIPTION_INACTIVE),
                        snapshot.attempts,
                    )
                )
                continue

            try:
                # pywebpush 是阻塞调用：放进线程，避免卡住事件循环。
                result = await asyncio.to_thread(
                    self._sender.send, snapshot.target, snapshot.payload.as_dict()
                )
            except Exception as exc:  # 发送器自身异常按可重试处理
                result = PushSendResult(SEND_OUTCOME_RETRYABLE, type(exc).__name__)
            results.append((snapshot, result, snapshot.attempts + 1))

        async with self._session_factory() as session:
            await self._apply_results(session, results, summary)
            await session.commit()
        return summary

    async def _load_batch(self) -> list[_JobSnapshot]:
        """抢占一批待执行作业，再读取事实；会话关闭后才进入发送阶段。

        抢占用条件 UPDATE（``status=pending AND claimed_at IS NULL``），与任务执行器
        的认领语义一致：多实例下同一个作业最多被一个执行者拿到。
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        stale_before = now - datetime.timedelta(
            seconds=max(60.0, self._timeout_seconds * 4)
        )
        async with self._session_factory() as session:
            # 回收崩溃执行者遗留的旧租约。
            await session.execute(
                update(PushJob)
                .where(
                    PushJob.status == PUSH_JOB_STATUS_PENDING,
                    PushJob.claimed_at.is_not(None),
                    PushJob.claimed_at < stale_before,
                )
                .values(claimed_at=None)
            )
            candidates = (
                await session.execute(
                    select(PushJob.id)
                    .where(
                        PushJob.status == PUSH_JOB_STATUS_PENDING,
                        PushJob.claimed_at.is_(None),
                    )
                    .order_by(PushJob.created_at.asc(), PushJob.id.asc())
                    .limit(self.batch_size)
                )
            ).scalars().all()
            claimed_ids: list[int] = []
            for job_id in candidates:
                result = await session.execute(
                    update(PushJob)
                    .where(
                        PushJob.id == job_id,
                        PushJob.status == PUSH_JOB_STATUS_PENDING,
                        PushJob.claimed_at.is_(None),
                    )
                    .values(claimed_at=now)
                )
                if result.rowcount == 1:
                    claimed_ids.append(job_id)
            await session.commit()
            if not claimed_ids:
                return []
            rows = (
                await session.execute(
                    select(PushJob, ReminderDelivery, PushSubscription)
                    .join(
                        ReminderDelivery,
                        PushJob.delivery_id == ReminderDelivery.id,
                        isouter=True,
                    )
                    .join(
                        PushSubscription,
                        PushJob.subscription_id == PushSubscription.id,
                        isouter=True,
                    )
                    .where(PushJob.id.in_(claimed_ids))
                    .order_by(PushJob.created_at.asc(), PushJob.id.asc())
                )
            ).all()

            snapshots: list[_JobSnapshot] = []
            for job, delivery, subscription in rows:
                if delivery is None:
                    snapshots.append(
                        _JobSnapshot(
                            job_id=job.id,
                            delivery_id=job.delivery_id,
                            subscription_id=job.subscription_id,
                            attempts=job.attempts,
                            payload=None,
                            target=None,
                            subscription_active=False,
                            error=ERROR_DELIVERY_MISSING,
                        )
                    )
                    continue

                target = None
                if subscription is not None and subscription.user_id != job.user_id:
                    snapshots.append(
                        _JobSnapshot(
                            job_id=job.id,
                            delivery_id=job.delivery_id,
                            subscription_id=job.subscription_id,
                            attempts=job.attempts,
                            payload=self._payload_of(delivery),
                            target=None,
                            subscription_active=False,
                            error=ERROR_SUBSCRIPTION_OWNER_MISMATCH,
                        )
                    )
                    continue
                if subscription is not None:
                    target = PushTarget(
                        subscription_id=subscription.id,
                        endpoint=subscription.endpoint,
                        p256dh=subscription.p256dh,
                        auth=subscription.auth,
                    )
                snapshots.append(
                    _JobSnapshot(
                        job_id=job.id,
                        delivery_id=job.delivery_id,
                        subscription_id=job.subscription_id,
                        attempts=job.attempts,
                        payload=self._payload_of(delivery),
                        target=target,
                        subscription_active=bool(
                            subscription is not None and subscription.is_active
                        ),
                    )
                )
            return snapshots

    @staticmethod
    def _payload_of(delivery: ReminderDelivery) -> _DeliveryPayload:
        source = delivery.payload if isinstance(delivery.payload, dict) else {}
        return _DeliveryPayload(
            title=str(source.get("title") or ""),
            body=str(source.get("body") or ""),
            target_path=str(source.get("target_path") or "/dashboard"),
        )

    async def _apply_results(
        self,
        session: AsyncSession,
        results: list[tuple[_JobSnapshot, PushSendResult, int]],
        summary: dict,
    ) -> None:
        """把发送结果收敛到作业 / 投递记录 / 订阅三处（同一短事务）。"""
        now = datetime.datetime.now(datetime.timezone.utc)
        for snapshot, result, attempts in results:
            job = await session.get(PushJob, snapshot.job_id)
            if job is None or job.status != PUSH_JOB_STATUS_PENDING:
                continue
            delivery = await session.get(ReminderDelivery, snapshot.delivery_id)
            subscription = await session.get(PushSubscription, snapshot.subscription_id)

            job.claimed_at = None
            if result.outcome == SEND_OUTCOME_SENT:
                job.status = PUSH_JOB_STATUS_SENT
                job.attempts = attempts
                job.last_error = None
                if delivery is not None:
                    delivery.status = DELIVERY_STATUS_SENT
                    delivery.error_summary = None
                if subscription is not None:
                    subscription.is_active = True
                    subscription.failure_reason = None
                    subscription.last_success_at = now
                summary["sent"] += 1
                self._log_send(EVENT_PUSH_SEND_SENT, snapshot, result, attempts)
                continue

            if result.outcome == SEND_OUTCOME_INVALID:
                self._fail_job(job, delivery, result.detail, attempts)
                if subscription is not None:
                    # 推送服务明确说订阅不存在：永久失效，后续 tick 不再投递。
                    subscription.is_active = False
                    subscription.failure_reason = SUBSCRIPTION_FAILURE_ENDPOINT_GONE
                summary["failed"] += 1
                self._log_send(EVENT_PUSH_SEND_INVALID, snapshot, result, attempts)
                continue

            if result.outcome == SEND_OUTCOME_RETRYABLE:
                job.attempts = attempts
                job.last_error = result.detail
                if attempts >= self.max_attempts:
                    # 达到重试上限：作业与投递记录一并失败，不留永远 pending 的作业。
                    job.status = PUSH_JOB_STATUS_FAILED
                    if delivery is not None:
                        delivery.status = DELIVERY_STATUS_FAILED
                        delivery.error_summary = result.detail
                    summary["failed"] += 1
                    self._log_send(EVENT_PUSH_SEND_FAILED, snapshot, result, attempts)
                else:
                    summary["retried"] += 1
                    self._log_send(EVENT_PUSH_SEND_RETRYABLE, snapshot, result, attempts)
                continue

            # 内部失败（订阅缺失/失效/投递缺失）：终态失败，不再重试。
            self._fail_job(job, delivery, result.detail, attempts)
            summary["failed"] += 1
            self._log_send(EVENT_PUSH_SEND_FAILED, snapshot, result, attempts)

    @staticmethod
    def _fail_job(
        job: PushJob,
        delivery: ReminderDelivery | None,
        detail: str | None,
        attempts: int,
    ) -> None:
        job.status = PUSH_JOB_STATUS_FAILED
        job.attempts = attempts
        job.last_error = detail
        if delivery is not None:
            delivery.status = DELIVERY_STATUS_FAILED
            delivery.error_summary = detail

    @staticmethod
    def _log_send(
        event: str,
        snapshot: _JobSnapshot,
        result: PushSendResult,
        attempts: int,
    ) -> None:
        fields: dict = {
            FIELD_JOB_ID: snapshot.job_id,
            FIELD_DELIVERY_ID: snapshot.delivery_id,
            FIELD_SUBSCRIPTION_ID: snapshot.subscription_id,
            FIELD_ATTEMPTS: attempts,
            FIELD_OUTCOME: result.outcome,
        }
        if snapshot.target is not None:
            fields[FIELD_ENDPOINT_HASH] = endpoint_fingerprint(snapshot.target.endpoint)
        if result.detail:
            fields[FIELD_ERROR_CODE] = result.detail
        log_event(
            logger,
            event,
            message="Web Push 发送结果",
            level=logging.WARNING if result.outcome != SEND_OUTCOME_SENT else logging.INFO,
            **fields,
        )


class PushJobWorker:
    """推送作业执行器的进程内周期宿主；start/stop 幂等，异常不杀循环。"""

    def __init__(
        self,
        session_factory: Callable = AsyncSessionLocal,
        sender: PushSender | None = None,
        interval_seconds: float | None = None,
        max_attempts: int | None = None,
    ):
        self._session_factory = session_factory
        self._sender = sender
        self.interval_seconds = (
            settings.PUSH_JOB_TICK_SECONDS if interval_seconds is None else interval_seconds
        )
        self._max_attempts = max_attempts
        self._task: asyncio.Task | None = None
        self._run_in_progress = False

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """启动循环；重复调用不会产生第二个长任务。"""
        if self.is_running:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """取消并等待循环结束；幂等。"""
        task, self._task = self._task, None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _loop(self) -> None:
        # 先睡再跑：启动瞬间不与滚动发布中的旧实例抢同一批作业。
        while True:
            await asyncio.sleep(self.interval_seconds)
            await self.run_once()

    async def run_once(self) -> dict:
        """执行一轮；任何异常都被捕获并记录，长任务不会因此死掉。"""
        if self._run_in_progress:
            return {"status": "skipped_reentrant"}

        self._run_in_progress = True
        try:
            executor = PushJobExecutor(
                sender=self._sender or WebPushSender(),
                session_factory=self._session_factory,
                max_attempts=self._max_attempts,
            )
            summary = await executor.run_once()
            return {"status": "ok", **summary}
        except Exception as exc:
            log_event(
                logger,
                EVENT_PUSH_WORKER_FAILED,
                message="推送作业执行失败，已捕获并继续",
                level=logging.ERROR,
                exc_info=exc,
                **{FIELD_ERROR_CLASS: type(exc).__name__},
            )
            return {"status": "error", "error_class": type(exc).__name__}
        finally:
            self._run_in_progress = False


__all__ = [
    "ERROR_CODE_PUSH_UNAVAILABLE",
    "SEND_OUTCOME_FAILED",
    "SEND_OUTCOME_INVALID",
    "SEND_OUTCOME_RETRYABLE",
    "SEND_OUTCOME_SENT",
    "PushJobExecutor",
    "PushJobWorker",
    "PushSendResult",
    "PushSender",
    "PushService",
    "PushTarget",
    "WebPushSender",
    "endpoint_fingerprint",
    "enqueue_web_push_delivery",
]
