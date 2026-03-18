from fastapi import APIRouter, Header

from app.schemas import store

router = APIRouter(prefix="/v1/home", tags=["home"])


@router.get("/workout")
async def home_workout(x_user_id: str = Header(default="u_demo")):
    profile = store.get_profile(x_user_id)
    return {
        "tab": "workout",
        "today_workout": {"name": "胸背力量强化训练", "duration_minutes": 45, "intensity": "中等"},
        "calendar": {"month": "2026-03", "highlight_days": [3, 5, 7, 8]},
        "ai_buddy": {
            "entry": "/pages/workout/ai-chat",
            "teaser": f"{profile['nickname']}，今天继续完成你的强化计划吗？",
        },
    }


@router.get("/diet")
async def home_diet(x_user_id: str = Header(default="u_demo")):
    total = sum(i["calories"] for i in store.diet_logs if i["user_id"] == x_user_id)
    return {
        "tab": "diet",
        "calorie_target": 2000,
        "calorie_consumed": total,
        "macro": {"protein": 125, "carb": 180, "fat": 62},
        "records": [i for i in store.diet_logs if i["user_id"] == x_user_id][-10:],
    }


@router.get("/progress")
async def home_progress(x_user_id: str = Header(default="u_demo")):
    profile = store.get_profile(x_user_id)
    report = store.get_weekly_report(x_user_id)
    return {
        "tab": "progress",
        "weight": profile["weight_kg"],
        "target_weight": profile["target_weight_kg"],
        "weekly_report_summary": report,
        "my_entry": {
            "sections": ["profile", "settings", "export", "account"],
            "path": "/pages/profile/index",
        },
    }
