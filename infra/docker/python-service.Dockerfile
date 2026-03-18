# Why: unified Python runtime image for all FastAPI services.
# Scope: api-gateway, profile-service, ai-coach-service, task-service containers.
# Verify: `docker compose build` succeeds for every service.
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY app /app/app

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

CMD ["python", "-m", "app.main"]