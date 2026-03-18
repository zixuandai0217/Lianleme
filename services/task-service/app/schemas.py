from datetime import date, timedelta
from uuid import uuid4

from pydantic import BaseModel


class PhotoAnalyzeRequest(BaseModel):
    user_id: str
    image_url: str
    mode: str = 'body_analysis'


TASKS: dict[str, dict] = {}


def create_photo_analysis_task(user_id: str, analysis_mode: str) -> dict:
    # Why: function and parameter names should reflect this is a photo-analysis task creation path.
    # Scope: photo analyze route task initialization and in-memory task storage fields.
    # Verify: `test_photo_task_lifecycle` still gets queued task_id and can query it by id.
    task_id = f'task_{uuid4().hex[:12]}'
    task = {'task_id': task_id, 'user_id': user_id, 'status': 'queued', 'mode': analysis_mode, 'result_summary': None}
    TASKS[task_id] = task
    return task


def build_sample_weekly_report(user_id: str) -> dict:
    week_end = date.today()
    week_start = week_end - timedelta(days=6)
    return {
        'user_id': user_id,
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'calories_in': 12450,
        'calories_out': 3850,
        'weight_change_kg': -0.8,
        'ai_suggestion': '本周你完成度不错，建议保持训练频次并继续稳定饮食。',
    }
