"""姿态会话的内存存储（工单 40）。

会话状态只活在进程内存里：不落库、不写文件、不写日志，进程重启即失效。
这样做不是图省事——关键点序列属于生物特征数据，持久化会与「训练结束即丢」直接冲突。

约束：
- 会话标识不透明（``pose_`` + token_urlsafe），只能由创建者使用；
- 空闲 30 分钟自动过期（每次成功请求都续期），过期后按 404 处理；
- 每用户最多 3 个进行中的会话，避免一个客户端无限开窗吃内存；
- 单会话 3600 帧硬上限，超出直接拒绝，绝不静默截断。
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.schemas.pose import CAMERA_VIEWS, DEFAULT_CAMERA_VIEW
from app.services.pose.evaluation import SCORE_DECIMALS, CycleEvaluation
from app.services.pose.segmentation import (
    CYCLE_STATE_COMPLETED,
    CYCLE_STATE_WAITING,
    DetectedCycle,
    SegmentationOutcome,
)

Frame = dict[str, Any]

SESSION_ID_PREFIX = "pose_"
SESSION_TTL_SECONDS = 30 * 60
MAX_ACTIVE_SESSIONS_PER_USER = 3
MAX_FRAMES_PER_SESSION = 3600


class PoseGraphProtocol(Protocol):
    """会话依赖姿态图的三个节点：接帧、切分与规则评估（识别/改写再往后扩展）。"""

    def ingest_frames(self, window: Sequence[Frame], new_frames: Sequence[Frame]) -> list[Frame]:
        ...

    def segment_cycle(
        self,
        frames: Sequence[Frame],
        *,
        camera_view: str = DEFAULT_CAMERA_VIEW,
    ) -> SegmentationOutcome:
        ...

    def evaluate_cycle(
        self,
        frames: Sequence[Frame],
        *,
        camera_view: str = DEFAULT_CAMERA_VIEW,
    ) -> CycleEvaluation:
        ...


class PoseSessionError(Exception):
    """姿态会话的可读错误；由路由层映射成稳定错误码与 HTTP 状态码。"""

    code = "pose_session_error"
    status_code = 400
    message = "姿态会话操作失败"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        self.detail = message or self.message


class PoseSessionNotFound(PoseSessionError):
    code = "pose_session_not_found"
    status_code = 404
    message = "姿态会话不存在或已过期，请重新开始"


class PoseSessionForbidden(PoseSessionError):
    code = "pose_session_forbidden"
    status_code = 403
    message = "无权访问其他用户的姿态会话"


class PoseSessionFinished(PoseSessionError):
    code = "pose_session_finished"
    status_code = 409
    message = "姿态会话已结束，请重新开始"


class PoseSessionLimitExceeded(PoseSessionError):
    code = "pose_session_limit"
    status_code = 429
    message = f"同时进行的姿态会话过多（最多 {MAX_ACTIVE_SESSIONS_PER_USER} 个），请先结束其中一个"


class PoseSessionFrameLimitExceeded(PoseSessionError):
    code = "pose_session_frame_limit"
    status_code = 413
    message = f"本次会话的帧数已达上限（{MAX_FRAMES_PER_SESSION} 帧），请结束会话后重新开始"


class PoseFramesOutOfOrder(PoseSessionError):
    code = "pose_frames_out_of_order"
    status_code = 422
    message = "帧时间戳必须单调不减：新帧的 t_ms 不能早于已接收的最后一帧"


@dataclass
class PoseSession:
    """一个姿态会话的全部内存状态；keypoints 只在这里短暂停留。"""

    session_id: str
    user_id: int
    camera_view: str
    exercise_hint: str | None
    created_at: float
    last_seen_at: float
    expires_at: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    pending_frames: list[Frame] = field(default_factory=list, repr=False)
    cycles: list[EvaluatedCycle] = field(default_factory=list, repr=False)
    frames_count: int = 0
    last_t_ms: int | None = None
    finished: bool = False

    @property
    def status(self) -> str:
        return "finished" if self.finished else "active"

    @property
    def cycle_state(self) -> str:
        return CYCLE_STATE_COMPLETED if self.cycles else CYCLE_STATE_WAITING


@dataclass(frozen=True)
class EvaluatedCycle:
    """会话里保存的一个周期：切分统计 + 规则评估结果。

    不可评估周期（机位/可见度问题）没有评估结果：``evaluation=None``，
    对外仍是 ``score=null``、``issues=[]``，绝不编造评分。
    """

    cycle: DetectedCycle
    evaluation: CycleEvaluation | None = None


@dataclass(frozen=True)
class FramePushOutcome:
    """一次追加帧的结果：本批新完成的周期 + 会话累计计数。"""

    new_cycles: tuple[EvaluatedCycle, ...]
    cycles_count: int
    frames_count: int


@dataclass(frozen=True)
class SessionSnapshot:
    """取结果用的只读快照。"""

    session_id: str
    status: str
    cycle_state: str
    cycles: tuple[EvaluatedCycle, ...]
    frames_count: int

    @property
    def cycles_count(self) -> int:
        return len(self.cycles)


@dataclass(frozen=True)
class SessionSummary:
    """结束会话时的聚合摘要：只保留数值，不保留任何关键点。"""

    session_id: str
    cycles_count: int
    evaluable_cycles: int
    not_evaluable_cycles: int
    frames_count: int
    # 只对已评估周期求平均；quality_available=False 表示这次会话没有真实评分。
    avg_quality: float = 0.0
    issues_histogram: dict[str, int] = field(default_factory=dict)
    quality_available: bool = False


class PoseSessionStore:
    """按用户隔离、带空闲过期的内存会话表。"""

    def __init__(
        self,
        *,
        ttl_seconds: int = SESSION_TTL_SECONDS,
        max_sessions_per_user: int = MAX_ACTIVE_SESSIONS_PER_USER,
        max_frames_per_session: int = MAX_FRAMES_PER_SESSION,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_sessions_per_user = max_sessions_per_user
        self.max_frames_per_session = max_frames_per_session
        self._clock = clock
        self._sessions: dict[str, PoseSession] = {}
        self._registry_lock = asyncio.Lock()

    # --- 会话生命周期 -----------------------------------------------------

    async def create_session(
        self,
        *,
        user_id: int,
        camera_view: str = DEFAULT_CAMERA_VIEW,
        exercise_hint: str | None = None,
    ) -> PoseSession:
        """创建会话；同一用户的进行中会话达到上限时抛 429 语义错误。"""
        async with self._registry_lock:
            now = self._clock()
            self._purge_expired(now)
            active = sum(
                1 for session in self._sessions.values()
                if session.user_id == user_id and not session.finished
            )
            if active >= self.max_sessions_per_user:
                raise PoseSessionLimitExceeded()
            session = PoseSession(
                session_id=SESSION_ID_PREFIX + secrets.token_urlsafe(24),
                user_id=user_id,
                camera_view=camera_view if camera_view in CAMERA_VIEWS else DEFAULT_CAMERA_VIEW,
                exercise_hint=exercise_hint,
                created_at=now,
                last_seen_at=now,
                expires_at=now + self.ttl_seconds,
            )
            self._sessions[session.session_id] = session
            return session

    async def get_session(
        self,
        session_id: str,
        *,
        user_id: int,
        allow_finished: bool = False,
    ) -> PoseSession:
        """取出属于该用户的会话；不存在/过期 404，他人 403，已结束 409。"""
        async with self._registry_lock:
            now = self._clock()
            self._purge_expired(now)
            session = self._sessions.get(session_id)
            if session is None:
                raise PoseSessionNotFound()
            if session.user_id != user_id:
                raise PoseSessionForbidden()
            if session.finished and not allow_finished:
                raise PoseSessionFinished()
            self._touch(session, now)
            return session

    async def append_frames(
        self,
        session: PoseSession,
        frames: Sequence[Frame],
        *,
        graph: PoseGraphProtocol,
    ) -> FramePushOutcome:
        """追加一批帧：校验会话状态与上限后交给姿态图切分。"""
        async with session.lock:
            now = self._clock()
            if session.finished:
                raise PoseSessionFinished()
            # 并发窗口保护：get_session 之后、拿到会话锁之前，另一个请求可能把它回收掉。
            if now - session.last_seen_at >= self.ttl_seconds:
                async with self._registry_lock:
                    self._sessions.pop(session.session_id, None)
                raise PoseSessionNotFound()
            if session.frames_count + len(frames) > self.max_frames_per_session:
                raise PoseSessionFrameLimitExceeded()
            self._ensure_monotonic(session, frames)

            window = graph.ingest_frames(session.pending_frames, frames)
            outcome = graph.segment_cycle(window, camera_view=session.camera_view)

            # 周期帧窗口只在这里短暂存在：规则评估后立即丢弃，不进入会话状态。
            completed = tuple(
                EvaluatedCycle(
                    cycle=completed_window.cycle,
                    evaluation=(
                        graph.evaluate_cycle(
                            completed_window.frames,
                            camera_view=session.camera_view,
                        )
                        if completed_window.cycle.evaluable
                        else None
                    ),
                )
                for completed_window in outcome.completed
            )
            session.pending_frames = list(outcome.pending_frames)
            session.cycles.extend(completed)
            session.frames_count += len(frames)
            session.last_t_ms = int(frames[-1]["t_ms"])
            self._touch(session, now)
            return FramePushOutcome(
                new_cycles=completed,
                cycles_count=len(session.cycles),
                frames_count=session.frames_count,
            )

    async def snapshot(self, session: PoseSession) -> SessionSnapshot:
        """在会话锁内取一致快照，避免读到半个周期。"""
        async with session.lock:
            return SessionSnapshot(
                session_id=session.session_id,
                status=session.status,
                cycle_state=session.cycle_state,
                cycles=tuple(session.cycles),
                frames_count=session.frames_count,
            )

    async def finish_session(self, session: PoseSession) -> SessionSummary:
        """结束会话并返回聚合摘要；重复结束幂等，未成周期的窗口立即丢弃。"""
        async with session.lock:
            session.finished = True
            session.pending_frames = []
            self._touch(session, self._clock())
            evaluable = sum(1 for item in session.cycles if item.cycle.evaluable)
            scores = [
                item.evaluation.score
                for item in session.cycles
                if item.evaluation is not None
            ]
            histogram: dict[str, int] = {}
            for item in session.cycles:
                if item.evaluation is None:
                    continue
                for issue in item.evaluation.issues:
                    histogram[issue.type] = histogram.get(issue.type, 0) + 1
            return SessionSummary(
                session_id=session.session_id,
                cycles_count=len(session.cycles),
                evaluable_cycles=evaluable,
                not_evaluable_cycles=len(session.cycles) - evaluable,
                frames_count=session.frames_count,
                avg_quality=(
                    round(sum(scores) / len(scores), SCORE_DECIMALS) if scores else 0.0
                ),
                issues_histogram=histogram,
                quality_available=bool(scores),
            )

    # --- 内部 -------------------------------------------------------------

    def _touch(self, session: PoseSession, now: float) -> None:
        """每次成功请求都续期，空闲超时才过期。"""
        session.last_seen_at = now
        session.expires_at = now + self.ttl_seconds

    def _purge_expired(self, now: float) -> None:
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.last_seen_at >= self.ttl_seconds
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)

    @staticmethod
    def _ensure_monotonic(session: PoseSession, frames: Sequence[Frame]) -> None:
        """帧时间戳必须单调不减：既防乱序插入，也防客户端时间回拨。"""
        previous = session.last_t_ms
        for frame in frames:
            t_ms = int(frame["t_ms"])
            if previous is not None and t_ms < previous:
                raise PoseFramesOutOfOrder()
            previous = t_ms


_default_store = PoseSessionStore()


def get_pose_session_store() -> PoseSessionStore:
    """FastAPI 依赖：进程内共享的会话表（测试通过依赖覆盖注入独立实例）。"""
    return _default_store
