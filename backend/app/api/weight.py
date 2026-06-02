"""体重记录路由：新增/查询趋势/删除"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import ensure_current_user_matches, get_current_user
from app.models.user import User
from app.schemas.weight import WeightRecordCreate, WeightRecordResponse, WeightTrendResponse
from app.services.weight.weight_service import WeightService

router = APIRouter()


@router.post("/record", response_model=WeightRecordResponse)
async def add_weight(
    req: WeightRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """记录体重（同一天重复提交会覆盖）"""
    ensure_current_user_matches(current_user, req.user_id)
    service = WeightService(db)
    return await service.add_record(req)


@router.get("/{user_id}/trend", response_model=WeightTrendResponse)
async def get_weight_trend(
    user_id: int,
    days: int = Query(90, ge=7, le=365, description="查询最近多少天"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取体重趋势（默认最近 90 天）"""
    ensure_current_user_matches(current_user, user_id)
    service = WeightService(db)
    return await service.get_trend(user_id, days)


@router.delete("/{user_id}/{record_id}")
async def delete_weight(
    user_id: int,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除一条体重记录"""
    ensure_current_user_matches(current_user, user_id)
    service = WeightService(db)
    deleted = await service.delete_record(user_id, record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"message": "已删除"}
