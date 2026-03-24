import re
from datetime import date, datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str


class ProfileRequest(BaseModel):
    nickname: str
    height_cm: float
    weight_kg: float
    target_weight_kg: float


class CoachMessageRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


class PlanGenerateRequest(BaseModel):
    user_id: str
    plan_type: str
    objective: str


class DietLogRequest(BaseModel):
    user_id: str
    meal_type: str
    calories: int


class WorkoutLogRequest(BaseModel):
    user_id: str
    workout_name: str
    duration_minutes: int
    calories_burned: int


class PhotoAnalyzeRequest(BaseModel):
    user_id: str
    image_url: str
    mode: str = "body_analysis"


class InMemoryStore:
    def __init__(self) -> None:
        self.tokens: dict[str, str] = {}
        self.accounts: dict[str, dict] = {}
        self.profiles: dict[str, dict] = {}
        self.diet_logs: list[dict] = []
        self.workout_logs: list[dict] = []
        self.photo_tasks: dict[str, dict] = {}

    def normalize_email(self, email: str) -> str:
        return email.strip().lower()

    def build_user_id(self, email: str) -> str:
        normalized_email = self.normalize_email(email)
        local_part = normalized_email.split("@", 1)[0]
        stable_slug = re.sub(r"[^a-z0-9]+", "_", local_part).strip("_") or "demo"
        return f"u_{stable_slug[:24]}"

    def issue_token(self, email: str) -> str:
        # simplify demo auth identity to email-based sessions so the mobile client can use one low-friction form; gateway mock auth only; verify with `uv run --with pytest pytest tests/test_gateway.py -k auth -q`.
        token = f"tok_{uuid4().hex[:16]}"
        self.tokens[token] = self.normalize_email(email)
        return token

    def register_account(self, email: str, password: str) -> dict:
        # keep mock registration state minimal but stable so register and later login can speak the same email contract; gateway in-memory auth only; verify with `uv run --with pytest pytest tests/test_gateway.py -k auth -q`.
        normalized_email = self.normalize_email(email)
        account = {
            "email": normalized_email,
            "password": password,
            "user_id": self.build_user_id(normalized_email),
        }
        self.accounts[normalized_email] = account
        return account

    def get_profile(self, user_id: str) -> dict:
        return self.profiles.get(
            user_id,
            {
                "user_id": user_id,
                "nickname": "练了么用户",
                "height_cm": 170,
                "weight_kg": 70,
                "target_weight_kg": 65,
            },
        )

    def set_profile(self, user_id: str, payload: dict) -> dict:
        profile = {"user_id": user_id, **payload}
        self.profiles[user_id] = profile
        return profile

    def add_diet_log(self, payload: dict) -> dict:
        item = {**payload, "logged_at": datetime.utcnow().isoformat()}
        self.diet_logs.append(item)
        return item

    def add_workout_log(self, payload: dict) -> dict:
        item = {**payload, "logged_at": datetime.utcnow().isoformat()}
        self.workout_logs.append(item)
        return item

    def create_photo_task(self, user_id: str) -> dict:
        task_id = f"task_{uuid4().hex[:12]}"
        task = {
            "task_id": task_id,
            "user_id": user_id,
            "status": "queued",
            "result_summary": None,
        }
        self.photo_tasks[task_id] = task
        return task

    def get_weekly_report(self, user_id: str) -> dict:
        week_end = date.today()
        week_start = week_end - timedelta(days=6)
        calories_in = sum(i["calories"] for i in self.diet_logs if i["user_id"] == user_id)
        calories_out = sum(i["calories_burned"] for i in self.workout_logs if i["user_id"] == user_id)
        return {
            "user_id": user_id,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "calories_in": calories_in,
            "calories_out": calories_out,
            "weight_change_kg": -0.6,
            "ai_suggestion": "本周你在能量缺口上表现稳定，建议继续保持每周4次训练。",
        }


store = InMemoryStore()
