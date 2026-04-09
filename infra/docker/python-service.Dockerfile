# ── Stage 1: 构建依赖（builder）──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# 安装编译依赖（只在 builder 阶段需要，不进入最终镜像）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 利用 Docker 层缓存：依赖文件不变时跳过重新安装
COPY pyproject.toml uv.lock ./

# 用 uv 从 lockfile 导出精确依赖，安装到 /install 目录
RUN pip install --no-cache-dir uv \
    && uv export --frozen --no-dev --no-hashes -o requirements.txt \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt \
    && rm requirements.txt


# ── Stage 2: 运行镜像（runtime）──────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# 仅安装运行时必需的系统库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 拷贝已安装的 Python 包
COPY --from=builder /install /usr/local

# 创建非 root 用户，降低容器权限
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 拷贝应用代码
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

# 生产环境：1 个 worker（适配 2核2G 服务器），关闭 reload
# 升级到 2核4G 后可将 --workers 改为 2
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
