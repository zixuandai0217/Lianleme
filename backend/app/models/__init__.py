"""models 包：导出所有 ORM 模型，确保 SQLAlchemy metadata 注册完整"""
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.user import User

__all__ = ["User", "TrainingPlan", "WorkoutRecord"]
