"""训练记录路由：上报训练完成数据、查询打卡统计、推进训练会话"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ensure_current_user_matches, get_current_user
from app.models.user import User
from app.models.workout_session import WorkoutSession
from app.schemas.workout import CheckInStatsResponse, WorkoutCompleteRequest, WorkoutRecordResponse
from app.schemas.workout_session import (
    CompleteSetRequest,
    SkipExerciseRequest,
    StartSessionRequest,
    WorkoutSessionView,
)
from app.services.workout.session_service import (
    ERROR_STATUS,
    SessionError,
    WorkoutSessionService,
)
from app.services.workout.workout_service import WorkoutService

router = APIRouter()


@router.post("/complete", response_model=WorkoutRecordResponse)
async def complete_workout(
    req: WorkoutCompleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    训练完成上报：记录打卡数据 + 触发计划动态调整
    完成率 ≥80% 自动调高下周难度，<50% 调低
    """
    ensure_current_user_matches(current_user, req.user_id)
    service = WorkoutService(db)
    record = await service.complete_workout(req)
    return record


def _session_error(exc: SessionError) -> HTTPException:
    """Map a session business failure onto its stable HTTP status + error code."""
    return HTTPException(
        status_code=ERROR_STATUS.get(exc.code, 400),
        detail={"code": exc.code, "message": exc.message},
    )


async def _owned_session(
    service: WorkoutSessionService, session_id: str, current_user: User
) -> WorkoutSession:
    """Load a session and enforce ownership; 404 for unknown, 403 for someone else's."""
    session = await service.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": "找不到这次训练会话"},
        )
    ensure_current_user_matches(current_user, session.user_id)
    return session


# 会话路由必须声明在 /{user_id}/... 之前，避免 "sessions" 被当成用户标识解析。
@router.post("/sessions/start", response_model=WorkoutSessionView)
async def start_workout_session(
    req: StartSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """开始今天的训练（同日重复调用返回同一个会话；休息日 / 无计划返回稳定错误码）。"""
    ensure_current_user_matches(current_user, req.user_id)
    service = WorkoutSessionService(db)
    try:
        session = await service.start(req.user_id)
    except SessionError as exc:
        raise _session_error(exc) from exc
    return service.view(session)


@router.get("/sessions/current", response_model=WorkoutSessionView)
async def get_current_session(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """读取今天正在进行（或刚结束）的会话；没有会话时返回 404 + no_session。"""
    ensure_current_user_matches(current_user, user_id)
    service = WorkoutSessionService(db)
    session = await service.current(user_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail={"code": "no_session", "message": "今天还没有开始训练"}
        )
    return service.view(session)


@router.get("/sessions/{session_id}", response_model=WorkoutSessionView)
async def read_workout_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按标识读取会话（退出后再次进入的恢复入口）。"""
    service = WorkoutSessionService(db)
    session = await _owned_session(service, session_id, current_user)
    return service.view(session)


@router.post("/sessions/{session_id}/sets", response_model=WorkoutSessionView)
async def complete_session_set(
    session_id: str,
    req: CompleteSetRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """完成一组：同一组重复提交幂等，进度不回退。"""
    service = WorkoutSessionService(db)
    await _owned_session(service, session_id, current_user)
    try:
        session = await service.complete_set(session_id, req.exercise_index, req.set_index)
    except SessionError as exc:
        raise _session_error(exc) from exc
    return service.view(session)


@router.post("/sessions/{session_id}/skip", response_model=WorkoutSessionView)
async def skip_session_exercise(
    session_id: str,
    req: SkipExerciseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """跳过动作（必须带原因）：动作留在明细里，但不计入完成组数。"""
    service = WorkoutSessionService(db)
    await _owned_session(service, session_id, current_user)
    try:
        session = await service.skip_exercise(session_id, req.exercise_index, req.reason)
    except SessionError as exc:
        raise _session_error(exc) from exc
    return service.view(session)


@router.get("/{user_id}/stats", response_model=CheckInStatsResponse)
async def get_checkin_stats(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取用户打卡统计（连续天数、总次数、本月完成率）"""
    ensure_current_user_matches(current_user, user_id)
    service = WorkoutService(db)
    return await service.get_stats(user_id)


@router.get("/{user_id}/calendar")
async def get_calendar(
    user_id: int,
    year: int = None,
    month: int = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定月份打卡日历数据（用于个人中心月历视图）"""
    ensure_current_user_matches(current_user, user_id)
    import datetime
    today = datetime.date.today()
    service = WorkoutService(db)
    return await service.get_monthly_calendar(
        user_id=user_id,
        year=year or today.year,
        month=month or today.month,
    )
