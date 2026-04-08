"""
PushService：微信订阅消息推送封装 + APScheduler 定时任务
每日定时推送训练提醒给已订阅用户
"""
import logging
from datetime import datetime

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.utils.wx_client import WxClient

logger = logging.getLogger(__name__)

# 全局调度器实例
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


class PushService:
    """微信订阅消息推送服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.wx = WxClient()

    async def send_workout_reminder(self, user_openid: str, template_id: str) -> bool:
        """发送单条训练提醒订阅消息"""
        try:
            await self.wx.send_subscribe_message(
                openid=user_openid,
                template_id=template_id,
                data={
                    "thing1": {"value": "今日训练提醒"},
                    "time2": {"value": datetime.now().strftime("%H:%M")},
                    "thing3": {"value": "点击开始训练，保持打卡连续！"},
                },
            )
            return True
        except Exception as e:
            logger.warning(f"推送失败 openid={user_openid}: {e}")
            return False

    async def batch_send_reminders(self, template_id: str) -> dict:
        """批量推送每日训练提醒（定时任务调用）"""
        result = await self.db.execute(select(User.openid).where(User.openid.isnot(None)))
        openids = [row.openid for row in result]
        success, fail = 0, 0
        for openid in openids:
            ok = await self.send_workout_reminder(openid, template_id)
            if ok:
                success += 1
            else:
                fail += 1
        logger.info(f"批量推送完成：成功 {success}，失败 {fail}")
        return {"success": success, "fail": fail}


def setup_scheduler():
    """注册定时推送任务（FastAPI lifespan 启动时调用）"""
    from app.core.database import AsyncSessionLocal

    @scheduler.scheduled_job("cron", hour=8, minute=0, id="daily_workout_reminder")
    async def daily_reminder():
        """每日 8:00 推送训练提醒"""
        async with AsyncSessionLocal() as session:
            service = PushService(session)
            template_id = "your_wechat_subscribe_template_id"
            await service.batch_send_reminders(template_id)

    if not scheduler.running:
        scheduler.start()
    logger.info("APScheduler 已启动：每日 08:00 训练提醒任务已注册")
