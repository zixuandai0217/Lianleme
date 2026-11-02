"""models 包：导出所有 ORM 模型，确保 SQLAlchemy metadata 注册完整"""
from app.models.adjustment import PlanAdjustment
from app.models.adjustment_job import PlanAdjustmentJob
from app.models.admin_export_audit import AdminExportAudit
from app.models.analysis_task import AnalysisTask
from app.models.body_analysis import BodyAnalysisRecord
from app.models.chat_message import ChatMessageRecord
from app.models.media_asset import MediaAsset
from app.models.plan import TrainingPlan
from app.models.pose_aggregate import PoseQualityAggregate
from app.models.push import PushJob, PushSubscription
from app.models.record import WorkoutRecord
from app.models.reminder import ReminderDelivery
from app.models.reminder_preference import ReminderPreference
from app.models.user import User
from app.models.weight import WeightRecord
from app.models.workout_session import WorkoutSession

__all__ = [
    "User", "TrainingPlan", "WorkoutRecord", "WeightRecord",
    "BodyAnalysisRecord", "ChatMessageRecord", "AnalysisTask", "PlanAdjustment",
    "ReminderDelivery", "ReminderPreference", "WorkoutSession", "AdminExportAudit",
    "MediaAsset",
    "PlanAdjustmentJob",
    "PoseQualityAggregate",
    "PushSubscription",
    "PushJob",
]
