"""FastAPI 应用入口：注册路由、CORS 中间件、请求关联、全局异常处理"""

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.api import admin, coach, media, notification, plan, user, vision, weight, workout
from app.core.config import settings
from app.core.database import engine
from app.core.health import APP_VERSION, build_readiness, liveness_report
from app.core.logging import (
    ERROR_CODE_HTTP_PREFIX,
    EVENT_HTTP_FAILED,
    FIELD_DURATION_MS,
    FIELD_ERROR_CLASS,
    FIELD_ERROR_CODE,
    FIELD_METHOD,
    FIELD_ROUTE,
    FIELD_STATUS_CODE,
    configure_logging,
    log_event,
    root_cause,
)
from app.core.observability import (
    RequestContextMiddleware,
    mark_expected_failure,
    route_template,
)
from app.core.request_context import (
    REQUEST_ID_HEADER,
    bind_request_context,
    new_request_id,
)
from app.core.storage import ensure_bucket_exists
from app.models import record  # noqa: F401 触发 ORM 注册
from app.services.reminder.scheduler import ReminderScheduler

configure_logging(
    app_env=settings.APP_ENV,
    level=settings.LOG_LEVEL,
    log_format=settings.LOG_FORMAT,
)

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
INDEX_TEMPLATE = TEMPLATE_DIR / "index.html"


def uses_orm_bootstrap() -> bool:
    """是否用 ORM 元数据建表。

    只有开发环境的 SQLite 才允许这么做；生产库（Postgres 或任何非开发环境）只走迁移，
    否则「迁移与 ORM 对齐」这条约定会因为启动时偷偷建表而失效。
    """
    return settings.APP_ENV == "development" and settings.DATABASE_URL.startswith("sqlite")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：开发环境建表 + 确保 MinIO bucket + 启停提醒调度宿主"""
    if uses_orm_bootstrap():
        from app.core.database import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    ensure_bucket_exists()

    scheduler = ReminderScheduler()
    app.state.reminder_scheduler = scheduler
    if settings.REMINDER_ENABLED:
        scheduler.start()

    try:
        yield
    finally:
        # 先停调度再释放连接池：否则 tick 可能在引擎关闭后仍尝试写库。
        await scheduler.stop()
        await engine.dispose()


app = FastAPI(
    title="练了么 - AI 健身教练",
    version=APP_VERSION,
    lifespan=lifespan,
)

# CORS（开发环境放开，生产按域名限制）
# 请求标识必须放进允许暴露列表，否则浏览器端读不到响应头。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.APP_ENV == "development" else settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)

# 请求关联中间件放在最外层：先确定请求标识，再进入业务与异常处理
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局兜底异常处理：记录带堆栈的错误事件，对外只返回安全文案"""
    state = request.scope.setdefault("state", {})
    request_id = state.get("request_id") or new_request_id()
    started = state.get("request_started")

    fields: dict = {
        FIELD_METHOD: request.scope.get("method"),
        FIELD_ROUTE: route_template(request.scope),
        FIELD_STATUS_CODE: 500,
        FIELD_ERROR_CODE: f"{ERROR_CODE_HTTP_PREFIX}500",
        FIELD_ERROR_CLASS: type(root_cause(exc)).__name__,
    }
    if started is not None:
        fields[FIELD_DURATION_MS] = round((time.perf_counter() - started) * 1000, 3)

    with bind_request_context(request_id=request_id, user_id=state.get("user_id")):
        log_event(
            logger,
            EVENT_HTTP_FAILED,
            message="未处理异常",
            level=logging.ERROR,
            exc_info=(type(exc), exc, exc.__traceback__),
            **fields,
        )

    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误，请稍后重试"},
        headers={REQUEST_ID_HEADER: request_id},
    )


# 注册路由
app.include_router(user.router, prefix="/api/user", tags=["用户"])
app.include_router(vision.router, prefix="/api/vision", tags=["体型分析"])
app.include_router(media.router, prefix="/api/media", tags=["媒体资产"])
app.include_router(plan.router, prefix="/api/plan", tags=["训练计划"])
app.include_router(coach.router, prefix="/api/coach", tags=["AI 陪练"])
app.include_router(workout.router, prefix="/api/workout", tags=["训练记录"])
app.include_router(weight.router, prefix="/api/weight", tags=["体重记录"])
app.include_router(notification.router, prefix="/api/notifications", tags=["站内通知"])
app.include_router(admin.router, prefix="/api/admin", tags=["管理后台"])


@app.get("/health")
async def health():
    """存活检查：只回答进程还在不在，永远不探测外部依赖。"""
    return liveness_report()


@app.get("/health/ready")
async def health_ready(request: Request):
    """就绪检查：逐项探测依赖，必需依赖不可用时返回 503 让流量被摘走。"""
    report, status_code = await build_readiness()
    if status_code >= 500:
        # 依赖不可用是探针的正常结论，不该按未处理异常刷 error 日志
        mark_expected_failure(request.scope)
    return JSONResponse(status_code=status_code, content=report)


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    """默认首页：读取独立 HTML 模板作为域名访问入口。"""
    return HTMLResponse(content=INDEX_TEMPLATE.read_text(encoding="utf-8"), status_code=200)
