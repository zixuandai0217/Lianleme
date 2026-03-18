import asyncio


async def analyze_photo(worker_context, task_id: str, image_url: str, analysis_mode: str) -> dict:
    # Why: worker_context/analysis_mode are clearer than ctx/mode for async worker jobs.
    # Scope: ARQ photo-analysis job parameter naming inside task-service worker functions.
    # Verify: worker registration still references `analyze_photo` and task payload shape stays unchanged.
    _ = worker_context
    await asyncio.sleep(0.1)
    return {
        'task_id': task_id,
        'status': 'done',
        'result_summary': f'识别完成({analysis_mode})，建议保持核心收紧并控制晚餐总热量。',
        'image_url': image_url,
    }


async def build_weekly_report(worker_context, user_id: str) -> dict:
    _ = worker_context
    await asyncio.sleep(0.05)
    return {
        'user_id': user_id,
        'calories_in': 12450,
        'calories_out': 3850,
        'weight_change_kg': -0.8,
        'ai_suggestion': '本周减重节奏稳定，建议下周增加一次力量训练。',
    }
