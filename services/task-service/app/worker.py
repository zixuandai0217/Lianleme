import os
from arq.connections import RedisSettings

from app.tasks.jobs import analyze_photo, build_weekly_report


class WorkerSettings:
    # Why: centralize ARQ registration to keep async task behavior consistent.
    # Scope: photo analysis and weekly report background execution.
    # Verify: `arq app.worker.WorkerSettings` can load functions.
    functions = [analyze_photo, build_weekly_report]
    redis_settings = RedisSettings.from_dsn(os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
