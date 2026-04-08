from pydantic import BaseModel, Field


class Settings(BaseModel):
    service_name: str = Field(default="api-gateway")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=18000)
    profile_service_base_url: str = Field(default="http://localhost:18010")
    ai_coach_service_base_url: str = Field(default="http://localhost:18020")
    task_service_base_url: str = Field(default="http://localhost:18030")


def load_settings() -> Settings:
    import os

    # shift the standalone gateway defaults away from crowded 80xx ports; local api-gateway startup and downstream discovery only; verify with http://127.0.0.1:18000/health plus proxied v1 routes
    return Settings(
        service_name=os.getenv("SERVICE_NAME", "api-gateway"),
        port=int(os.getenv("PORT", "18000")),
        profile_service_base_url=os.getenv("PROFILE_SERVICE_BASE_URL", "http://localhost:18010"),
        ai_coach_service_base_url=os.getenv("AI_COACH_SERVICE_BASE_URL", "http://localhost:18020"),
        task_service_base_url=os.getenv("TASK_SERVICE_BASE_URL", "http://localhost:18030"),
    )


settings = load_settings()
