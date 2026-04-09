FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖声明文件以利用 Docker 层缓存（依赖不变时跳过重新安装）
COPY pyproject.toml uv.lock ./
# 安装 uv，从 lockfile 精确导出并安装生产依赖到系统 Python
RUN pip install --no-cache-dir uv \
    && uv export --frozen --no-dev --no-hashes -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt \
    && rm requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
