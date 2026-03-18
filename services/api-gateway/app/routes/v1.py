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
    WorkoutLogRequest,
    store,
)

router = APIRouter(prefix="/v1", tags=["v1"])


@router.post("/auth/login")
async def login(payload: LoginRequest):
    token = store.issue_token(payload.phone)
    return {"access_token": token, "token_type": "bearer", "user_id": f"u_{payload.phone[-4:]}"}


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
    return {"name": "鑳歌儗鍔涢噺寮哄寲璁粌", "duration_minutes": 45, "cta": "寮€濮嬭缁?}


@router.post("/workout/logs")
async def create_workout_log(payload: WorkoutLogRequest):
    return store.add_workout_log(payload.model_dump())


@router.get("/diet/today")
async def diet_today():
    return {
        "daily_target": 2000,
        "suggestions": ["鏃╅澧炲姞铔嬬櫧璐?, "鍗堥鎺у埗娌硅剛", "鏅氶琛ュ厖钄彍"],
    }


@router.post("/diet/logs")
async def create_diet_log(payload: DietLogRequest):
    return store.add_diet_log(payload.model_dump())


@router.post("/coach/message")
async def coach_message(payload: CoachMessageRequest):
    service_response = await post_json(settings.ai_coach_service_base_url, "/internal/coach/message", payload.model_dump())
    return service_response or {
        "session_id": payload.session_id,
        "reply": "缁х画淇濇寔锛屼粖澶╁厛鍋氱儹韬?0鍒嗛挓锛屽啀杩涘叆涓昏缁冦€?,
    }


@router.post("/plan/generate")
async def plan_generate(payload: PlanGenerateRequest):
    service_response = await post_json(settings.ai_coach_service_base_url, "/internal/plan/generate", payload.model_dump())
    return service_response or {
        "plan_id": f"plan_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "plan_type": payload.plan_type,
        "summary": "宸茬敓鎴?澶╄缁冧笌楗寤鸿",
    }


@router.post("/plan/regenerate")
async def plan_regenerate(payload: PlanGenerateRequest):
    service_response = await post_json(settings.ai_coach_service_base_url, "/internal/plan/regenerate", payload.model_dump())
    return service_response or {
        "plan_id": f"plan_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "plan_type": payload.plan_type,
        "summary": "宸查噸鏂扮敓鎴愯鍒?,
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
            {"recipe_id": "r1", "name": "鎵嬫挄楦¤兏鑲?, "calories": 210, "tag": "楂樿泲鐧?},
            {"recipe_id": "r2", "name": "榛勭摐娌欐媺", "calories": 85, "tag": "浣庣⒊姘?},
        ]
    }


@router.get("/admin/workout-templates")
async def admin_workout_templates():
    return {
        "items": [
            {"template_id": "w1", "name": "鍑忚剛鍏ラ棬4鍛?, "level": "beginner"},
            {"template_id": "w2", "name": "鐕冭剛闂存瓏璁粌", "level": "intermediate"},
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


