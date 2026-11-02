"""可查询的调整作业：打卡后异步评估的持久事实（工单 26）。

打卡响应只负责创建这条作业并把评估投递出去；作业状态与结果全部回写数据库，
因此刷新页面、换设备或进程重启后，读取路径不依赖任何内存注册表。

状态词表：``evaluating | pending_choice | applied | expired_no_choice | failed``。
``pending_choice``（等待用户在三选一中拍板）与 ``expired_no_choice``（超时后按
推荐方案落地）属于工单 27 的 interrupt 流程；工单 26 只生产 ``evaluating`` /
``applied`` / ``failed``，但表结构与读取形状已经为后两者预留，避免二次改表。
"""
import datetime
import time
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.compat import JSONB
from app.core.database import Base

JOB_STATUS_EVALUATING = "evaluating"
JOB_STATUS_PENDING_CHOICE = "pending_choice"
JOB_STATUS_APPLIED = "applied"
JOB_STATUS_EXPIRED_NO_CHOICE = "expired_no_choice"
JOB_STATUS_FAILED = "failed"

ADJUSTMENT_JOB_STATUSES = (
    JOB_STATUS_EVALUATING,
    JOB_STATUS_PENDING_CHOICE,
    JOB_STATUS_APPLIED,
    JOB_STATUS_EXPIRED_NO_CHOICE,
    JOB_STATUS_FAILED,
)

# 未决状态：用户之后回到计划页需要能发现它们。
PENDING_JOB_STATUSES = (JOB_STATUS_EVALUATING, JOB_STATUS_PENDING_CHOICE)

# 进程在评估途中崩溃时，作业会停在 evaluating；读取时按「超时即投影为失败」收敛，
# 保证它既不会永远占着未决列表，也不会被误报成已落地。
STALE_EVALUATING_SECONDS = 15 * 60
FAILURE_CLASS_INTERRUPTED = "interrupted"
ERROR_CODE_EVALUATION_INTERRUPTED = "evaluation_interrupted"
ERROR_CODE_JOB_NOT_FOUND = "adjustment_job_not_found"
ERROR_CODE_JOB_FORBIDDEN = "adjustment_job_forbidden"


def _as_utc(value: datetime.datetime | None) -> datetime.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def is_stale_evaluating(
    job: "PlanAdjustmentJob", now: datetime.datetime | None = None
) -> bool:
    """评估中且超过收敛窗口没有任何更新：视为进程中断。"""
    if job.status != JOB_STATUS_EVALUATING:
        return False
    updated = _as_utc(job.updated_at)
    if updated is None:
        return False
    moment = now or datetime.datetime.now(datetime.timezone.utc)
    return (moment - updated).total_seconds() >= STALE_EVALUATING_SECONDS


def effective_status(
    job: "PlanAdjustmentJob", now: datetime.datetime | None = None
) -> str:
    """对外状态：中断的评估投影为 failed，其余原样返回。"""
    return JOB_STATUS_FAILED if is_stale_evaluating(job, now) else job.status


def effective_failure_class(
    job: "PlanAdjustmentJob", now: datetime.datetime | None = None
) -> str | None:
    return FAILURE_CLASS_INTERRUPTED if is_stale_evaluating(job, now) else job.failure_class


def effective_error_code(
    job: "PlanAdjustmentJob", now: datetime.datetime | None = None
) -> str | None:
    return ERROR_CODE_EVALUATION_INTERRUPTED if is_stale_evaluating(job, now) else job.error_code


def effective_landed(
    job: "PlanAdjustmentJob", now: datetime.datetime | None = None
) -> bool:
    return effective_status(job, now) in (JOB_STATUS_APPLIED, JOB_STATUS_EXPIRED_NO_CHOICE)


def new_job_id() -> str:
    """时间有序、不可猜测的对外作业标识：``job_`` + 16 hex 时间 + 8 hex 随机。

    与调整结论的 ``adj_`` 标识同构：SQLite 的 ``CURRENT_TIMESTAMP`` 只有秒精度，
    时间前缀让「按 job_id 倒序」等价于创建顺序，同秒内投递多个作业也不会漂移。
    """
    return f"job_{time.time_ns():016x}{uuid4().hex[:8]}"


class PlanAdjustmentJob(Base):
    """一次打卡触发的调整作业及其可查询结果。"""

    __tablename__ = "plan_adjustment_jobs"

    job_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=JOB_STATUS_EVALUATING
    )
    # 成功落地后指向 plan_adjustments 的那条结论；空值表示尚未落地。
    adjustment_id: Mapped[str | None] = mapped_column(
        ForeignKey("plan_adjustments.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    landed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 评估时快照的计划前后差异：之后计划再变也不会改写这次调整的交代。
    plan_diff: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    interrupt: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index(
            "ux_plan_adjustment_jobs_adjustment_id",
            "adjustment_id",
            unique=True,
        ),
        Index("ix_plan_adjustment_jobs_user_created_at", "user_id", "created_at"),
        Index("ix_plan_adjustment_jobs_status_created_at", "status", "created_at"),
    )
