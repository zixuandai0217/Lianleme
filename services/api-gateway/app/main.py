# Why: expose public `/v1/*` API with trace_id middleware and structured logs.
# Scope: all client-facing endpoints are served by this process.
# Verify: call `/health` and `/v1/home/workout` and inspect `x-trace-id` header.
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.logging_config import configure_logging
from app.routes.home import router as home_router
from app.routes.v1 import router as v1_router

configure_logging(settings.service_name)
logger = logging.getLogger(__name__)

app = FastAPI(title="Lianleme API Gateway", version="1.0.0")


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["x-trace-id"] = trace_id
    return response


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("unhandled error", extra={"trace_id": getattr(request.state, "trace_id", "n/a")})
    return JSONResponse(status_code=500, content={"message": "internal error", "trace_id": getattr(request.state, "trace_id", "n/a")})


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.service_name}


app.include_router(home_router)
app.include_router(v1_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)

