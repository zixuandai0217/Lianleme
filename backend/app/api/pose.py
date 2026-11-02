"""姿态纠错路由：创建会话 → 追加帧 → 取结果 → 结束（工单 40）。

会话资源只活在进程内存里；本层负责鉴权、所有权、上限校验与稳定错误码，
不保留任何帧：帧批交给 ``PoseGraph.ingest_frames`` / ``segment_cycle`` 后，
未成周期的窗口回到会话内存，周期只留时间与质量统计。
"""

import datetime
import math

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.pose import (
    MAX_FRAMES_PER_BATCH,
    UPLOAD_INTERVAL_MS,
    PoseCycle,
    PoseFinishResponse,
    PoseFramesRequest,
    PoseFramesResponse,
    PoseResultResponse,
    PoseSessionCreate,
    PoseSessionResponse,
)
from app.services.ai.pose_graph import PoseGraph
from app.services.pose.segmentation import (
    DetectedCycle,
)
from app.services.pose.session_store import (
    PoseSessionError,
    PoseSessionStore,
    get_pose_session_store,
)

router = APIRouter()

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


def get_pose_graph() -> PoseGraph:
    """姿态图依赖：测试覆盖成计数替身，用来断言接帧与切分的调用次数。"""
    return PoseGraph()


def _cycle_response(cycle: DetectedCycle) -> PoseCycle:
    """周期只暴露时间与质量统计：没有关键点、没有编造的评分。"""
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
        score=None,
        issues=[],
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
):
    """结束会话并返回聚合摘要；重复结束幂等，未成周期的窗口立即丢弃。"""
    try:
        session = await store.get_session(
            session_id, user_id=current_user.id, allow_finished=True
        )
        summary = await store.finish_session(session)
    except PoseSessionError as exc:
        raise _session_http_error(exc) from None

    return PoseFinishResponse(
        session_id=summary.session_id,
        cycles_count=summary.cycles_count,
        evaluable_cycles=summary.evaluable_cycles,
        not_evaluable_cycles=summary.not_evaluable_cycles,
        frames_total=summary.frames_count,
        avg_quality=summary.avg_quality,
        issues_histogram=summary.issues_histogram,
        quality_available=summary.quality_available,
    )
