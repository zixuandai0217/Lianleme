"""WeightService：体重记录 CRUD + 趋势统计"""
import datetime
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.weight import WeightRecord
from app.schemas.weight import WeightRecordCreate, WeightRecordResponse, WeightTrendResponse


class WeightService:
    """体重记录核心服务：增删查 + 趋势分析"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_record(self, req: WeightRecordCreate) -> WeightRecordResponse:
        """新增或更新当天体重记录（同一天只保留一条）"""
        date = req.recorded_date or datetime.date.today()

        existing = await self.db.execute(
            select(WeightRecord).where(
                WeightRecord.user_id == req.user_id,
                WeightRecord.recorded_date == date,
            )
        )
        record = existing.scalar_one_or_none()

        if record:
            record.weight = req.weight
            record.note = req.note
        else:
            record = WeightRecord(
                user_id=req.user_id,
                weight=req.weight,
                recorded_date=date,
                note=req.note,
            )
            self.db.add(record)

        await self.db.flush()
        return WeightRecordResponse.model_validate(record)

    async def get_trend(
        self,
        user_id: int,
        days: int = 90,
    ) -> WeightTrendResponse:
        """获取体重趋势：最近 N 天的记录 + 统计摘要"""
        since = datetime.date.today() - datetime.timedelta(days=days)

        result = await self.db.execute(
            select(WeightRecord)
            .where(
                WeightRecord.user_id == user_id,
                WeightRecord.recorded_date >= since,
            )
            .order_by(WeightRecord.recorded_date.asc())
        )
        records = list(result.scalars().all())
        items = [WeightRecordResponse.model_validate(r) for r in records]

        if not items:
            return WeightTrendResponse(records=[], total=0)

        weights = [r.weight for r in items]
        return WeightTrendResponse(
            records=items,
            total=len(items),
            current_weight=items[-1].weight,
            start_weight=items[0].weight,
            min_weight=min(weights),
            max_weight=max(weights),
            change=round(items[-1].weight - items[0].weight, 2),
        )

    async def delete_record(self, user_id: int, record_id: int) -> bool:
        """删除一条体重记录"""
        result = await self.db.execute(
            delete(WeightRecord).where(
                WeightRecord.id == record_id,
                WeightRecord.user_id == user_id,
            )
        )
        return result.rowcount > 0
