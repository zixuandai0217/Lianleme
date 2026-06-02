"""models 包：导出所有 ORM 模型，确保 SQLAlchemy metadata 注册完整"""
from app.models.body_analysis import BodyAnalysisRecord
from app.models.chat_message import ChatMessageRecord
from app.models.plan import TrainingPlan
from app.models.record import WorkoutRecord
from app.models.user import User
from app.models.weight import WeightRecord

__all__ = [
    "User", "TrainingPlan", "WorkoutRecord", "WeightRecord",
    "BodyAnalysisRecord", "ChatMessageRecord",
]
