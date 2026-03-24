from datetime import datetime, timezone

from fastapi import APIRouter, Header

from app.clients import get_json, post_json
from app.config import settings
from app.schemas import (
    CoachMessageRequest,
    DietLogRequest,
    LoginRequest,
    PhotoAnalyzeRequest,
    PlanGenerateRequest,
    ProfileRequest,
    RegisterRequest,
    WorkoutLogRequest,
    store,
)

router = APIRouter(prefix="/v1", tags=["v1"])


def build_auth_response(email: str) -> dict:
    # simplify auth responses to one email/password contract so the mobile H5 shell can treat login and register the same way; gateway auth endpoints only; verify with `uv run --with pytest pytest tests/test_gateway.py -k auth -q`.
    normalized_email = store.normalize_email(email)
    token = store.issue_token(normalized_email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": store.build_user_id(normalized_email),
        "email": normalized_email,
    }


@router.post("/auth/login")
async def login(payload: LoginRequest):
    return build_auth_response(payload.email)


@router.post("/auth/register")
async def register(payload: RegisterRequest):
    # keep registration auto-login for now so the simplified client flow has no second auth step; gateway auth endpoints only; verify with `uv run --with pytest pytest tests/test_gateway.py -k auth -q`.
    store.register_account(payload.email, payload.password)
    return build_auth_response(payload.email)


@router.post("/auth/logout")
async def logout():
    return {"ok": True}


@router.get("/auth/me")
async def get_current_user(x_user_id: str = Header(default="u_demo")):
    return {"user_id": x_user_id, "nickname": store.get_profile(x_user_id)["nickname"]}


@router.get("/profile")
async def get_profile(x_user_id: str = Header(default="u_demo")):
    # Why: use service_response naming to clarify data origin in gateway aggregation.
    # Scope: profile, coach, plan, photo, and report proxy flows in v1 routes.
    # Verify: gateway route tests still return either service_response payload or local fallback.
    service_response = await get_json(settings.profile_service_base_url, f"/internal/users/{x_user_id}/profile")
    return service_response or store.get_profile(x_user_id)


@router.put("/profile")
async def update_profile(payload: ProfileRequest, x_user_id: str = Header(default="u_demo")):
    service_response = await post_json(
        settings.profile_service_base_url,
        f"/internal/users/{x_user_id}/profile",
        payload.model_dump(),
    )
    return service_response or store.set_profile(x_user_id, payload.model_dump())


@router.get("/profile/trend")
async def profile_trend():
    return {
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "weights": [72.5, 72.2, 71.8, 71.5, 71.3, 71.2, 71.1],
    }


@router.get("/workout/today")
async def workout_today():
    # Why: restore readable fallback copy and valid quoting after encoding corruption.
    # Scope: static fallback payload text used by workout/diet/coach/plan/admin APIs in gateway.
    # Verify: `uv run python -m compileall app` and smoke calls on `/v1/*` return 200 with readable text.
    return {"name": "胸背力量强化训练", "duration_minutes": 45, "cta": "开始训练"}


@router.post("/workout/logs")
async def create_workout_log(payload: WorkoutLogRequest):
    return store.add_workout_log(payload.model_dump())


@router.get("/diet/today")
async def diet_today():
    return {
        "daily_target": 2000,
        "suggestions": ["早餐增加蛋白质", "午餐控制油脂", "晚餐补充蔬菜"],
    }


@router.post("/diet/logs")
async def create_diet_log(payload: DietLogRequest):
    return store.add_diet_log(payload.model_dump())


@router.post("/coach/message")
async def coach_message(payload: CoachMessageRequest):
    service_response = await post_json(settings.ai_coach_service_base_url, "/internal/coach/message", payload.model_dump())
    return service_response or {
        "session_id": payload.session_id,
        "reply": "继续保持，今天先做热身10分钟，再进入主训练。",
    }


@router.post("/plan/generate")
async def plan_generate(payload: PlanGenerateRequest):
    service_response = await post_json(settings.ai_coach_service_base_url, "/internal/plan/generate", payload.model_dump())
    return service_response or {
        "plan_id": f"plan_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "plan_type": payload.plan_type,
        "summary": "已生成7天训练与饮食建议",
    }


@router.post("/plan/regenerate")
async def plan_regenerate(payload: PlanGenerateRequest):
    service_response = await post_json(settings.ai_coach_service_base_url, "/internal/plan/regenerate", payload.model_dump())
    return service_response or {
        "plan_id": f"plan_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "plan_type": payload.plan_type,
        "summary": "已重新生成计划",
    }


@router.post("/photo/analyze")
async def photo_analyze(payload: PhotoAnalyzeRequest):
    service_response = await post_json(settings.task_service_base_url, "/internal/photo/analyze", payload.model_dump())
    if service_response:
        return service_response
    fallback_task = store.create_photo_task(payload.user_id)
    return fallback_task


@router.get("/photo/tasks/{task_id}")
async def get_photo_task_status(task_id: str):
    service_response = await get_json(settings.task_service_base_url, f"/internal/photo/tasks/{task_id}")
    return service_response or store.photo_tasks.get(
        task_id,
        {"task_id": task_id, "status": "failed", "result_summary": "task not found"},
    )


@router.get("/report/weekly")
async def get_weekly_report(x_user_id: str = Header(default="u_demo")):
    service_response = await get_json(settings.task_service_base_url, f"/internal/report/weekly/{x_user_id}")
    return service_response or store.get_weekly_report(x_user_id)


@router.get("/admin/dashboard")
async def admin_dashboard():
    return {
        "users_total": 12840,
        "daily_active": 1250,
        "workouts_total": 45200,
        "calories_burned_total": 1200000,
    }


@router.get("/admin/users")
async def admin_users():
    return {
        "items": [
            {"user_id": "u_1001", "nickname": "Sarah", "weight_kg": 64.2, "goal_weight_kg": 58.0},
            {"user_id": "u_1002", "nickname": "Marcus", "weight_kg": 92.5, "goal_weight_kg": 85.0},
        ],
        "total": 2,
    }


@router.get("/admin/recipes")
async def admin_recipes():
    return {
        "items": [
            {"recipe_id": "r1", "name": "手撕鸡胸肉", "calories": 210, "tag": "高蛋白"},
            {"recipe_id": "r2", "name": "黄瓜沙拉", "calories": 85, "tag": "低碳水"},
        ]
    }


@router.get("/admin/workout-templates")
async def admin_workout_templates():
    return {
        "items": [
            {"template_id": "w1", "name": "减脂入门4周", "level": "beginner"},
            {"template_id": "w2", "name": "燃脂间歇训练", "level": "intermediate"},
        ]
    }


@router.get("/admin/ai-config")
async def admin_ai_config():
    return {
        "text_model": "deepseek-v3.2",
        "vision_model": "qwen3-vl-flash",
        "voice_enabled": False,
        "safety_mode": "health_management_only",
    }
