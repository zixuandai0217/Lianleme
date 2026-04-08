"""训练记录路由：上报训练完成数据、查询打卡统计"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.workout import CheckInStatsResponse, WorkoutCompleteRequest, WorkoutRecordResponse
from app.services.workout.workout_service import WorkoutService

router = APIRouter()


@router.post("/complete", response_model=WorkoutRecordResponse)
async def complete_workout(req: WorkoutCompleteRequest, db: AsyncSession = Depends(get_db)):
    """
    训练完成上报：记录打卡数据 + 触发计划动态调整
    完成率 ≥80% 自动调高下周难度，<50% 调低
    """
    service = WorkoutService(db)
    record = await service.complete_workout(req)
    return record


@router.get("/{user_id}/stats", response_model=CheckInStatsResponse)
async def get_checkin_stats(user_id: int, db: AsyncSession = Depends(get_db)):
    """获取用户打卡统计（连续天数、总次数、本月完成率）"""
    service = WorkoutService(db)
    return await service.get_stats(user_id)


@router.get("/{user_id}/calendar")
async def get_calendar(user_id: int, year: int = None, month: int = None, db: AsyncSession = Depends(get_db)):
    """获取指定月份打卡日历数据（用于个人中心月历视图）"""
    import datetime
    today = datetime.date.today()
    service = WorkoutService(db)
    return await service.get_monthly_calendar(
        user_id=user_id,
        year=year or today.year,
        month=month or today.month,
    )
