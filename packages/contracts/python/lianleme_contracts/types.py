from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    user_id: str
    nickname: str = "练了么用户"
    height_cm: float = 170
    weight_kg: float = 70
    target_weight_kg: float = 65


class GoalPlan(BaseModel):
    plan_id: str
    plan_type: Literal["workout", "diet"]
    title: str
    summary: str


class CoachSession(BaseModel):
    session_id: str
    user_id: str
    last_message: str
    updated_at: datetime


class DietLog(BaseModel):
    user_id: str
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    calories: int
    logged_at: datetime


class WorkoutLog(BaseModel):
    user_id: str
    workout_name: str
    duration_minutes: int
    calories_burned: int
    logged_at: datetime


class PhotoAnalysisTask(BaseModel):
    task_id: str
    user_id: str
    status: Literal["queued", "processing", "done", "failed"] = "queued"
    result_summary: str | None = None


class WeeklyReport(BaseModel):
    user_id: str
    week_start: date
    week_end: date
    calories_in: int
    calories_out: int
    weight_change_kg: float = Field(default=0.0)
    ai_suggestion: str
