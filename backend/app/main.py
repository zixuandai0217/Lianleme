"""FastAPI 应用入口：注册路由、CORS 中间件、全局异常处理"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import coach, plan, user, vision, workout
from app.core.config import settings
from app.core.database import engine
from app.core.storage import ensure_bucket_exists
from app.models import record, plan as plan_model, user as user_model  # noqa: F401 触发 ORM 注册


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表 + 确保 MinIO bucket，关闭时释放连接池"""
    from app.core.database import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    ensure_bucket_exists()
    yield
    await engine.dispose()


app = FastAPI(
    title="练了么 - AI 健身教练",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS（开发环境放开，生产按域名限制）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.APP_ENV == "development" else settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局兜底异常处理，避免内部错误泄漏到客户端"""
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误，请稍后重试"},
    )


# 注册路由
app.include_router(user.router, prefix="/api/user", tags=["用户"])
app.include_router(vision.router, prefix="/api/vision", tags=["体型分析"])
app.include_router(plan.router, prefix="/api/plan", tags=["训练计划"])
app.include_router(coach.router, prefix="/api/coach", tags=["AI 陪练"])
app.include_router(workout.router, prefix="/api/workout", tags=["训练记录"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lianleme-api"}
