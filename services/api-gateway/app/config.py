from pydantic import BaseModel, Field


class Settings(BaseModel):
    service_name: str = Field(default="api-gateway")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    profile_service_base_url: str = Field(default="http://localhost:8010")
    ai_coach_service_base_url: str = Field(default="http://localhost:8020")
    task_service_base_url: str = Field(default="http://localhost:8030")


def load_settings() -> Settings:
    import os

    # Why: renamed env vars align with service directory names and reduce ambiguity.
    # Scope: all downstream calls from api-gateway to internal services.
    # Verify: `/v1/profile`, `/v1/coach/message`, `/v1/photo/analyze` keep returning 200.
    return Settings(
        service_name=os.getenv("SERVICE_NAME", "api-gateway"),
        port=int(os.getenv("PORT", "8000")),
        profile_service_base_url=os.getenv("PROFILE_SERVICE_BASE_URL", "http://localhost:8010"),
        ai_coach_service_base_url=os.getenv("AI_COACH_SERVICE_BASE_URL", "http://localhost:8020"),
        task_service_base_url=os.getenv("TASK_SERVICE_BASE_URL", "http://localhost:8030"),
    )


settings = load_settings()