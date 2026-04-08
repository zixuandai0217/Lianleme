import os
from arq.connections import RedisSettings

from app.tasks.jobs import analyze_photo, build_weekly_report


class WorkerSettings:
    # centralize ARQ registration while matching the remapped local Redis host port; background worker bootstrap only; verify with `arq app.worker.WorkerSettings`
    functions = [analyze_photo, build_weekly_report]
    redis_settings = RedisSettings.from_dsn(os.getenv('REDIS_URL', 'redis://localhost:16379/0'))
