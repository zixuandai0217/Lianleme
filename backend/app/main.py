"""
VibeFit API - 科学减肥健身应用后端

基于 FastAPI 构建的高性能异步 API 服务
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db, close_db
from app.api.v1 import auth, users, profiles, diet, workout, stats, ai_chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    print(f"[INFO] Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    print("[INFO] Database initialized")
    yield
    # 关闭时清理
    await close_db()
    print("[INFO] Application shutdown")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    description="科学减肥健身应用 API - 提供个性化饮食计划、运动训练、AI 健康顾问等功能",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 健康检查
@app.get("/health", tags=["Health"])
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/", tags=["Root"])
async def root():
    """根路径"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


# 注册路由
app.include_router(auth.router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(users.router, prefix="/api/v1/users", tags=["用户"])
app.include_router(profiles.router, prefix="/api/v1/profiles", tags=["身体数据"])
app.include_router(diet.router, prefix="/api/v1/diet", tags=["饮食计划"])
app.include_router(workout.router, prefix="/api/v1/workout", tags=["运动计划"])
app.include_router(stats.router, prefix="/api/v1/stats", tags=["统计"])
app.include_router(ai_chat.router, prefix="/api/v1/ai", tags=["AI 顾问"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
