"""
饮食记录模型
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class DietLog(Base):
    """饮食记录表"""

    __tablename__ = "diet_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("diet_plans.id"), nullable=True)

    # 记录信息
    log_date = Column(Date, nullable=False, index=True, comment="记录日期")
    meal_type = Column(String(20), nullable=False, comment="餐类型：breakfast/lunch/dinner/snack")

    # 食物详情 (JSON 格式)
    foods = Column(JSON, nullable=False, comment="食物列表")

    # 营养总计
    total_calories = Column(Integer, default=0, comment="总热量 kcal")
    total_protein = Column(Float, default=0, comment="总蛋白质 g")
    total_carbs = Column(Float, default=0, comment="总碳水 g")
    total_fat = Column(Float, default=0, comment="总脂肪 g")

    # 图片（拍照识别）
    image_url = Column(String(500), nullable=True, comment="图片 URL")

    # 备注
    notes = Column(Text, nullable=True, comment="备注")

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    user = relationship("User", back_populates="diet_logs")
