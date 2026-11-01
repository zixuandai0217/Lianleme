"""WeightService：体重记录 CRUD + 趋势统计 + 趋势解读"""
import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.record import WorkoutRecord
from app.models.user import User
from app.models.weight import WeightRecord
from app.schemas.weight import (
    WeightExtreme,
    WeightGoalInsight,
    WeightInsightResponse,
    WeightRecordCreate,
    WeightRecordResponse,
    WeightTrendResponse,
    WeightWeeklyComparison,
    WeightWindowInsight,
)

# 解读窗口统一定义：键为响应字段名，值为回溯天数（含锚点当天）
INSIGHT_WINDOWS = {"d7": 7, "d30": 30}
# 覆盖 30 天窗口与 4 个 ISO 周所需的最大回溯天数
INSIGHT_LOOKBACK_DAYS = 34
WEEKLY_WEEKS = 4
# 判定"持平"的体重变化下限（kg）
FLAT_CHANGE_EPSILON = 0.1
# 判定"已达目标体重"的差距下限（kg）：按 0.1 kg 的记录精度取其一半
TARGET_REACHED_EPSILON = 0.05
# 维持型目标（塑形 / 提升体能）的容差带：当前体重的 0.5%
MAINTENANCE_BAND_RATIO = 0.005
# 健身目标 -> 期望体重方向（无数值目标时按方向推断）
GOAL_DIRECTIONS = {"减脂": "down", "增肌": "up", "塑形": "hold", "提升体能": "hold"}


def _direction_of(change: float) -> str:
    """把已保留 1 位小数的变化量映射为方向词"""
    if change < 0:
        return "down"
    if change > 0:
        return "up"
    return "flat"


class WeightService:
    """体重记录核心服务：增删查 + 趋势分析 + 趋势解读"""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _today(self) -> datetime.date:
        """当前日期取数口，测试可替换以获得确定性窗口"""
        return datetime.date.today()

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

    async def get_insights(self, user_id: int) -> WeightInsightResponse:
        """获取体重趋势解读：锚点窗口、带日期极值、四周训练对照

        窗口锚点为最新一条记录的日期而非今天，因此几天没称重的用户仍能看到
        自己的最近 7 天；锚点距今天超过 7 天时标记数据陈旧。
        """
        today = self._today()
        profile = await self._load_profile(user_id)
        anchor = await self._latest_record_date(user_id)

        if anchor is None:
            empty_windows = {
                key: WeightWindowInsight(days=days, insufficient=True)
                for key, days in INSIGHT_WINDOWS.items()
            }
            return WeightInsightResponse(
                anchor_date=None,
                windows=empty_windows,
                weekly=[],
                training_data_available=False,
                goal=self._build_goal(profile, None, None),
            )

        records = await self._load_insight_records(user_id, anchor)
        windows = {
            key: self._build_window(records, anchor, days)
            for key, days in INSIGHT_WINDOWS.items()
        }
        weekly, training_available = await self._build_weekly(
            user_id, anchor, records, windows["d30"]
        )
        stale_days = max((today - anchor).days, 0)

        return WeightInsightResponse(
            anchor_date=anchor,
            is_stale=stale_days > 7,
            stale_days=stale_days,
            windows=windows,
            weekly=weekly,
            training_data_available=training_available,
            goal=self._build_goal(profile, records[-1].weight, windows["d30"]),
        )

    async def _load_profile(self, user_id: int) -> dict:
        """读取用户档案（JSONB dict），缺失时按空档案处理"""
        result = await self.db.execute(select(User.profile).where(User.id == user_id))
        return result.scalar_one_or_none() or {}

    @staticmethod
    def _goal(
        mode: str,
        verdict: str,
        reason: str,
        *,
        gap: float | None = None,
        target_weight: float | None = None,
        goal_label: str | None = None,
        expected_direction: str | None = None,
    ) -> WeightGoalInsight:
        """构造一条目标判定：各分支只填自己关心的字段，避免重复搬运整批参数"""
        return WeightGoalInsight(
            mode=mode,
            verdict=verdict,
            reason=reason,
            gap=gap,
            target_weight=target_weight,
            goal_label=goal_label,
            expected_direction=expected_direction,
        )

    @classmethod
    def _build_goal(
        cls,
        profile: dict,
        current_weight: float | None,
        month_window: WeightWindowInsight | None,
    ) -> WeightGoalInsight:
        """按档案目标判定当前体重走向：数值目标优先，其次方向推断

        判定只描述"当前体重与目标的差距 + 最近 30 天方向"，不下因果或医学结论。
        """
        target_weight = profile.get("target_weight")
        goal_label = profile.get("goal")
        change = month_window.change if month_window else None

        if target_weight is None:
            expected = GOAL_DIRECTIONS.get(goal_label)
            if expected is None:
                return cls._goal("none", "neutral", "no_goal")
            if current_weight is None or change is None:
                return cls._goal(
                    "direction",
                    "insufficient",
                    "insufficient_samples",
                    goal_label=goal_label,
                    expected_direction=expected,
                )
            if expected == "hold":
                within_band = abs(change) < current_weight * MAINTENANCE_BAND_RATIO
                verdict, reason = (
                    ("steady", "hold_within_band")
                    if within_band
                    else ("off_track", "drift_outside_band")
                )
            elif abs(change) < FLAT_CHANGE_EPSILON:
                verdict, reason = "steady", "change_within_flat_band"
            else:
                matched = _direction_of(change) == expected
                verdict = "on_track" if matched else "off_track"
                reason = (
                    "change_matches_goal_direction"
                    if matched
                    else "change_against_goal_direction"
                )
            return cls._goal(
                "direction",
                verdict,
                reason,
                goal_label=goal_label,
                expected_direction=expected,
            )

        if current_weight is None:
            return cls._goal(
                "numeric",
                "insufficient",
                "insufficient_samples",
                target_weight=target_weight,
                goal_label=goal_label,
            )

        raw_gap = current_weight - target_weight
        gap = round(raw_gap, 1)
        target_fields = {"target_weight": target_weight, "goal_label": goal_label}
        if abs(raw_gap) < TARGET_REACHED_EPSILON:
            return cls._goal(
                "numeric", "on_track", "target_reached", gap=gap, **target_fields
            )

        expected = "down" if target_weight < current_weight else "up"
        if change is None:
            return cls._goal(
                "numeric",
                "insufficient",
                "insufficient_samples",
                gap=gap,
                expected_direction=expected,
                **target_fields,
            )
        if abs(change) < FLAT_CHANGE_EPSILON:
            return cls._goal(
                "numeric",
                "steady",
                "change_within_flat_band",
                gap=gap,
                expected_direction=expected,
                **target_fields,
            )
        matched = _direction_of(change) == expected
        return cls._goal(
            "numeric",
            "on_track" if matched else "off_track",
            "change_matches_target" if matched else "change_against_target",
            gap=gap,
            expected_direction=expected,
            **target_fields,
        )

    async def _latest_record_date(self, user_id: int) -> datetime.date | None:
        """取用户最新一条体重记录的日期（作为所有窗口的锚点）"""
        result = await self.db.execute(
            select(WeightRecord.recorded_date)
            .where(WeightRecord.user_id == user_id)
            .order_by(WeightRecord.recorded_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _load_insight_records(
        self, user_id: int, anchor: datetime.date
    ) -> list[WeightRecord]:
        """读取锚点回溯窗口内的体重记录（升序，保证"最后一条 - 第一条"可算）"""
        since = anchor - datetime.timedelta(days=INSIGHT_LOOKBACK_DAYS)
        result = await self.db.execute(
            select(WeightRecord)
            .where(
                WeightRecord.user_id == user_id,
                WeightRecord.recorded_date >= since,
                WeightRecord.recorded_date <= anchor,
            )
            .order_by(WeightRecord.recorded_date.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    def _build_window(
        records: list[WeightRecord], anchor: datetime.date, days: int
    ) -> WeightWindowInsight:
        """构造一个锚点窗口的变化与极值；记录少于 2 条时不下变化结论"""
        start = anchor - datetime.timedelta(days=days - 1)
        window = [record for record in records if start <= record.recorded_date <= anchor]

        if not window:
            return WeightWindowInsight(days=days, insufficient=True)

        # 极值并列时取日期更近的一条
        lowest = min(window, key=lambda item: (item.weight, -item.recorded_date.toordinal()))
        highest = max(window, key=lambda item: (item.weight, item.recorded_date.toordinal()))
        change = None
        direction = "insufficient"
        if len(window) >= 2:
            change = round(window[-1].weight - window[0].weight, 1)
            direction = _direction_of(change)

        return WeightWindowInsight(
            days=days,
            start_date=start,
            end_date=anchor,
            sample_count=len(window),
            change=change,
            direction=direction,
            min=WeightExtreme(weight=lowest.weight, recorded_date=lowest.recorded_date),
            max=WeightExtreme(weight=highest.weight, recorded_date=highest.recorded_date),
            insufficient=len(window) < 2,
        )

    async def _build_weekly(
        self,
        user_id: int,
        anchor: datetime.date,
        records: list[WeightRecord],
        month_window: WeightWindowInsight,
    ) -> tuple[list[WeightWeeklyComparison], bool]:
        """构造最近 4 个 ISO 周的体重变化与训练天数对照

        返回 (周对照, 训练数据是否可读)；训练数据读不到时整体隐藏周对照，
        但不影响窗口变化与极值。
        """
        anchor_week_start = anchor - datetime.timedelta(days=anchor.weekday())
        week_starts = [
            anchor_week_start - datetime.timedelta(days=7 * offset)
            for offset in range(WEEKLY_WEEKS)
        ][::-1]

        earliest = min((record.recorded_date for record in records), default=anchor)
        week_starts = [
            week_start
            for week_start in week_starts
            if week_start + datetime.timedelta(days=6) >= earliest
        ]
        if not week_starts:
            return [], False

        try:
            training_dates = await self._load_training_dates(
                user_id,
                week_starts[0],
                week_starts[-1] + datetime.timedelta(days=6),
            )
        except Exception:
            return [], False

        entries: list[WeightWeeklyComparison] = []
        for week_start in week_starts:
            week_end = week_start + datetime.timedelta(days=6)
            week_records = [
                record for record in records if week_start <= record.recorded_date <= week_end
            ]
            change = None
            if len(week_records) >= 2:
                change = round(week_records[-1].weight - week_records[0].weight, 1)
            entries.append(
                WeightWeeklyComparison(
                    week_start=week_start,
                    week_end=week_end,
                    sample_count=len(week_records),
                    weight_change=change,
                    training_days=sum(
                        1 for workout_date in training_dates
                        if week_start <= workout_date <= week_end
                    ),
                    relation=self._weekly_relation(
                        change, len(week_records), month_window.direction
                    ),
                )
            )
        return entries, True

    @staticmethod
    def _weekly_relation(
        change: float | None, sample_count: int, window_direction: str
    ) -> str:
        """把该周变化与最近 30 天方向做描述性并列，不做因果推断"""
        if sample_count < 2 or change is None:
            return "insufficient"
        if abs(change) < FLAT_CHANGE_EPSILON:
            return "flat"
        if window_direction not in ("down", "up"):
            return "insufficient"
        same_direction = (change < 0) == (window_direction == "down")
        return "same" if same_direction else "reverse"

    async def _load_training_dates(
        self, user_id: int, start: datetime.date, end: datetime.date
    ) -> set[datetime.date]:
        """读取区间内不重复的训练日期（周对照的取数口）"""
        result = await self.db.execute(
            select(WorkoutRecord.workout_date).where(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.workout_date >= start,
                WorkoutRecord.workout_date <= end,
            )
        )
        return set(result.scalars().all())

    async def delete_record(self, user_id: int, record_id: int) -> bool:
        """删除一条体重记录"""
        result = await self.db.execute(
            delete(WeightRecord).where(
                WeightRecord.id == record_id,
                WeightRecord.user_id == user_id,
            )
        )
        return result.rowcount > 0
