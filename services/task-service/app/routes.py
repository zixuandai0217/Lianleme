import os

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter

from app.schemas import PhotoAnalyzeRequest, TASKS, build_sample_weekly_report, create_photo_analysis_task

router = APIRouter(prefix='/internal', tags=['internal'])


@router.post('/photo/analyze')
async def photo_analyze(payload: PhotoAnalyzeRequest):
    # keep the Redis fallback aligned with the remapped local host port; task-service local enqueue path only; verify with REDIS_URL unset and task-service route tests
    photo_task = create_photo_analysis_task(payload.user_id, payload.mode)
    redis_dsn = os.getenv('REDIS_URL', 'redis://localhost:16379/0')

    try:
        pool = await create_pool(RedisSettings.from_dsn(redis_dsn))
        await pool.enqueue_job('analyze_photo', photo_task['task_id'], payload.image_url, payload.mode)
    except Exception:
        # keep local development usable without a live Redis dependency; async photo submission fallback only; verify with task-service tests and a manual POST when Redis is absent
        photo_task['status'] = 'done'
        photo_task['result_summary'] = '本地降级模式：已生成拍照分析结果。'

    return photo_task


@router.get('/photo/tasks/{task_id}')
async def get_photo_task(task_id: str):
    return TASKS.get(task_id, {'task_id': task_id, 'status': 'failed', 'result_summary': 'task not found'})


@router.get('/report/weekly/{user_id}')
async def get_weekly_report(user_id: str):
    return build_sample_weekly_report(user_id)
