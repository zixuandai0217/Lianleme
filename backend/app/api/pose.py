"""姿态纠错路由：创建会话 → 追加帧 → 取结果 → 结束（工单 40）。

会话资源只活在进程内存里；本层负责鉴权、所有权、上限校验与稳定错误码，
不保留任何帧：帧批交给 ``PoseGraph.ingest_frames`` / ``segment_cycle`` 后，
未成周期的窗口回到会话内存，周期只留时间与质量统计。
"""

import datetime
import hashlib
import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import (
    EVENT_POSE_CYCLE_COMPLETED,
    EVENT_POSE_SESSION_FINISHED,
    FIELD_CYCLE_INDEX,
    FIELD_DURATION_MS,
    FIELD_ISSUE_TYPES,
    FIELD_SESSION,
    log_event,
)
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.pose import (
    MAX_FRAMES_PER_BATCH,
    UPLOAD_INTERVAL_MS,
    PoseAction,
    PoseAggregateListResponse,
    PoseAggregateResponse,
    PoseCycle,
    PoseFinishResponse,
    PoseFramesRequest,
    PoseFramesResponse,
    PoseHighlight,
    PoseInjurySummaryResponse,
    PoseIssue,
    PoseResultResponse,
    PoseSessionCreate,
    PoseSessionResponse,
)
from app.services.ai.pose_graph import PoseGraph
from app.services.pose import aggregate_service
from app.services.pose.llm_coach import PoseLLMCoach
from app.services.pose.session_store import (
    EvaluatedCycle,
    FramePushOutcome,
    PoseSessionError,
    PoseSessionStore,
    get_pose_session_store,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# 结构化日志事件：只记录会话短标识、周期序号、耗时与规则命中类型。
LOG_SESSION_ID_LENGTH = 8

# 创建会话时给的机位引导：一句话说清怎么架手机（画面不出设备）。
CREATE_CAMERA_HINT = "把手机架到与髋同高，确保全身入镜；正面或正侧拍摄都可以。"

ERROR_CODE_BATCH_TOO_LARGE = "pose_batch_too_large"
ERROR_MESSAGE_BATCH_TOO_LARGE = (
    f"单批帧数不能超过 {MAX_FRAMES_PER_BATCH} 帧，请减少每批帧数后重试"
)
ERROR_CODE_KEYPOINT_INVALID = "pose_keypoint_invalid"
ERROR_MESSAGE_KEYPOINT_INVALID = "关键点坐标与可见度必须是有限数值，且可见度在 0 到 1 之间"


def _validate_keypoints(frames: list[dict]) -> None:
    """坐标必须是有限数值：NaN / Infinity 会污染角度计算，必须在入口拒绝。

    放在路由层而不是 Pydantic 校验器里，是因为校验失败的响应会把原始值（含 NaN）
    一起回显，反而让 422 变成 500。
    """
    for frame in frames:
        for point in frame["keypoints"]:
            if not all(math.isfinite(point[name]) for name in ("x", "y", "z")):
                raise _http_error(ERROR_CODE_KEYPOINT_INVALID, 422, ERROR_MESSAGE_KEYPOINT_INVALID)
            visibility = point["visibility"]
            if not math.isfinite(visibility) or not 0.0 <= visibility <= 1.0:
                raise _http_error(ERROR_CODE_KEYPOINT_INVALID, 422, ERROR_MESSAGE_KEYPOINT_INVALID)


def _http_error(code: str, status_code: int, message: str) -> HTTPException:
    """统一 ``{"code","message"}`` 错误体；错误码是跨端契约，文案只在这里定义。"""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _session_http_error(exc: PoseSessionError) -> HTTPException:
    return _http_error(exc.code, exc.status_code, exc.detail)


def _aggregate_http_error(exc: aggregate_service.PoseAggregateError) -> HTTPException:
    return _http_error(exc.code, exc.status_code, exc.detail)


def _short_session_id(session_id: str) -> str:
    """日志用的会话短标识：哈希前 8 位，不可反推也不可直接当作会话 token。"""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:LOG_SESSION_ID_LENGTH]


def _log_completed_cycles(
    session_id: str,
    outcome: FramePushOutcome,
) -> None:
    """周期完成日志只带短标识、序号、耗时与问题类型，绝不含坐标/角度序列。"""
    first_index = outcome.cycles_count - len(outcome.new_cycles) + 1
    for offset, entry in enumerate(outcome.new_cycles):
        evaluation = entry.evaluation
        issue_types = sorted(
            {issue.type for issue in (evaluation.issues if evaluation is not None else ())}
        )
        log_event(
            logger,
            EVENT_POSE_CYCLE_COMPLETED,
            **{
                FIELD_SESSION: _short_session_id(session_id),
                FIELD_CYCLE_INDEX: first_index + offset,
                FIELD_DURATION_MS: entry.cycle.duration_ms,
                FIELD_ISSUE_TYPES: issue_types,
            },
        )


def get_pose_graph(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PoseGraph:
    """姿态图依赖：注入当前用户的 BYOK 教练；测试覆盖成计数/脚本化替身。"""
    return PoseGraph(coach=PoseLLMCoach(user_id=current_user.id, db=db))


def _cycle_response(entry: EvaluatedCycle) -> PoseCycle:
    """周期只暴露时间、质量统计、评估与增强结果：没有关键点、没有编造的评分。"""
    cycle = entry.cycle
    evaluation = entry.evaluation
    enhancement = entry.enhancement
    action = enhancement.action if enhancement is not None else None
    return PoseCycle(
        cycle_id=cycle.cycle_id,
        start_ms=cycle.start_ms,
        end_ms=cycle.end_ms,
        duration_ms=cycle.duration_ms,
        evaluable=cycle.evaluable,
        visibility_ratio=cycle.quality.visibility_ratio,
        out_of_frame_ratio=cycle.quality.out_of_frame_ratio,
        person_count=cycle.quality.person_count,
        reasons=list(cycle.quality.reasons),
        camera_hint=cycle.camera_hint,
        score=entry.final_score,
        issues=[
            PoseIssue(
                type=issue.type,
                severity=issue.severity,
                joints=list(issue.joints),
                hint=issue.hint,
            )
            for issue in (evaluation.issues if evaluation is not None else ())
        ]
        + [
            PoseIssue(
                type="model_observation",
                severity="info",
                joints=[],
                hint=observation,
            )
            for observation in (
                enhancement.info_issues if enhancement is not None else ()
            )
        ],
        highlights=[
            PoseHighlight(
                joints=list(highlight.joints),
                segments=[list(segment) for segment in highlight.segments],
                severity=highlight.severity,
                issue_type=highlight.issue_type,
            )
            for highlight in (evaluation.highlights if evaluation is not None else ())
        ],
        hint=enhancement.hint if enhancement is not None else (
            evaluation.hint if evaluation is not None else None
        ),
        action=(
            PoseAction(
                name=action.name,
                confidence=action.confidence,
                source=action.source,
            )
            if action is not None
            else None
        ),
        model_score=enhancement.model_score if enhancement is not None else None,
        feedback_source=enhancement.feedback_source if enhancement is not None else None,
        degraded=enhancement.degraded if enhancement is not None else False,
        degrade_reason=enhancement.degrade_reason if enhancement is not None else None,
        spoken=enhancement.spoken if enhancement is not None else True,
        notice=enhancement.notice if enhancement is not None else None,
    )


@router.post("/sessions", response_model=PoseSessionResponse)
async def create_pose_session(
    payload: PoseSessionCreate | None = None,
    current_user: User = Depends(get_current_user),
    store: PoseSessionStore = Depends(get_pose_session_store),
):
    """创建短生命周期会话；同一用户最多同时持有 3 个。"""
    request = payload or PoseSessionCreate()
    try:
        session = await store.create_session(
            user_id=current_user.id,
            camera_view=request.camera_view,
            exercise_hint=request.exercise_hint,
        )
    except PoseSessionError as exc:
        raise _session_http_error(exc) from None

    return PoseSessionResponse(
        session_id=session.session_id,
        camera_view=session.camera_view,
        ttl_seconds=store.ttl_seconds,
        expires_at=datetime.datetime.fromtimestamp(
            session.expires_at, tz=datetime.timezone.utc
        ),
        upload_interval_ms=UPLOAD_INTERVAL_MS,
        camera_hint=CREATE_CAMERA_HINT,
    )


@router.post("/sessions/{session_id}/frames", response_model=PoseFramesResponse)
async def append_pose_frames(
    session_id: str,
    payload: PoseFramesRequest,
    current_user: User = Depends(get_current_user),
    store: PoseSessionStore = Depends(get_pose_session_store),
    graph: PoseGraph = Depends(get_pose_graph),
):
    """追加一批帧；成周期就返回周期标识与起止，不成周期保持等待态。"""
    if len(payload.frames) > MAX_FRAMES_PER_BATCH:
        raise _http_error(
            ERROR_CODE_BATCH_TOO_LARGE, 413, ERROR_MESSAGE_BATCH_TOO_LARGE
        )

    frames = [frame.model_dump() for frame in payload.frames]
    _validate_keypoints(frames)
    try:
        session = await store.get_session(session_id, user_id=current_user.id)
        outcome = await store.append_frames(session, frames, graph=graph)
    except PoseSessionError as exc:
        raise _session_http_error(exc) from None

    _log_completed_cycles(session_id, outcome)
    cycles = [_cycle_response(cycle) for cycle in outcome.new_cycles]
    return PoseFramesResponse(
        accepted=len(frames),
        total_frames=outcome.frames_count,
        cycles_count=outcome.cycles_count,
        cycle_state=session.cycle_state,
        cycles=cycles,
    )


@router.get("/sessions/{session_id}/result", response_model=PoseResultResponse)
async def get_pose_result(
    session_id: str,
    current_user: User = Depends(get_current_user),
    store: PoseSessionStore = Depends(get_pose_session_store),
):
    """取会话至今已完成的周期；结束后再取结果返回 409。"""
    try:
        session = await store.get_session(session_id, user_id=current_user.id)
        snapshot = await store.snapshot(session)
    except PoseSessionError as exc:
        raise _session_http_error(exc) from None

    return PoseResultResponse(
        session_id=snapshot.session_id,
        status=snapshot.status,
        cycle_state=snapshot.cycle_state,
        cycles_count=snapshot.cycles_count,
        cycles=[_cycle_response(cycle) for cycle in snapshot.cycles],
    )


@router.post("/sessions/{session_id}/finish", response_model=PoseFinishResponse)
async def finish_pose_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    store: PoseSessionStore = Depends(get_pose_session_store),
    db: AsyncSession = Depends(get_db),
):
    """结束会话、返回聚合摘要并落一行数值聚合；重复结束幂等（复用同一行）。"""
    try:
        session = await store.get_session(
            session_id, user_id=current_user.id, allow_finished=True
        )
        summary = await store.finish_session(session)
    except PoseSessionError as exc:
        raise _session_http_error(exc) from None

    row = await aggregate_service.persist_session_aggregate(
        db,
        user_id=current_user.id,
        summary=summary,
        started_at=session.started_at,
        finished_at=session.finished_at or session.started_at,
    )
    log_event(
        logger,
        EVENT_POSE_SESSION_FINISHED,
        **{
            FIELD_SESSION: _short_session_id(session_id),
            FIELD_ISSUE_TYPES: sorted(summary.issues_histogram),
        },
    )

    return PoseFinishResponse(
        session_id=summary.session_id,
        cycles_count=summary.cycles_count,
        evaluable_cycles=summary.evaluable_cycles,
        not_evaluable_cycles=summary.not_evaluable_cycles,
        frames_total=summary.frames_count,
        avg_quality=summary.avg_quality,
        issues_histogram=summary.issues_histogram,
        quality_available=summary.quality_available,
        not_evaluable_ratio=aggregate_service.not_evaluable_ratio(
            summary.not_evaluable_cycles, summary.cycles_count
        ),
        aggregate_id=row.id,
        model_calls=summary.model_calls,
        degraded_cycles=summary.degraded_cycles,
        model_degraded=summary.model_degraded,
        circuit_open=summary.circuit_open,
        model_paused=summary.model_paused,
        paused_notice_sent=summary.paused_notice_sent,
    )


@router.get("/aggregates", response_model=PoseAggregateListResponse)
async def list_pose_aggregates(
    limit: int = Query(
        aggregate_service.DEFAULT_LIST_LIMIT,
        ge=1,
        le=aggregate_service.MAX_LIST_LIMIT,
        description="返回条数上限（有界）",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """自己的最近姿态聚合；只按 token 身份查询，不接受 user 参数。"""
    return await aggregate_service.list_aggregates(
        db, user_id=current_user.id, limit=limit
    )


@router.get("/aggregates/{aggregate_id}", response_model=PoseAggregateResponse)
async def get_pose_aggregate(
    aggregate_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读取自己的聚合详情；他人 403（无内容），不存在 404 稳定错误码。"""
    try:
        return await aggregate_service.get_aggregate(
            db, aggregate_id, user_id=current_user.id
        )
    except aggregate_service.PoseAggregateError as exc:
        raise _aggregate_http_error(exc) from None


@router.delete("/aggregates/{aggregate_id}", status_code=204)
async def delete_pose_aggregate(
    aggregate_id: int,
    current_user: User = Depends(get_current_user),
    store: PoseSessionStore = Depends(get_pose_session_store),
    db: AsyncSession = Depends(get_db),
):
    """硬删除自己的聚合，并同步丢弃会话内存：删除后不能通过重复结束重算。"""
    try:
        session_id = await aggregate_service.delete_aggregate(
            db, aggregate_id, user_id=current_user.id
        )
    except aggregate_service.PoseAggregateError as exc:
        raise _aggregate_http_error(exc) from None
    await store.discard_finished_session(session_id, user_id=current_user.id)
    return Response(status_code=204)


@router.get("/injury-summary", response_model=PoseInjurySummaryResponse)
async def get_pose_injury_summary(
    days: int = Query(
        aggregate_service.DEFAULT_INJURY_SUMMARY_DAYS,
        ge=1,
        le=aggregate_service.MAX_INJURY_SUMMARY_DAYS,
        description="统计最近多少天（只读数值摘要）",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """供伤病风险评估消费的只读摘要：只有数值聚合，没有关键点或单次明细。"""
    return await aggregate_service.build_injury_summary(
        db, user_id=current_user.id, days=days
    )
