# ── Base Image: 后端依赖层（依赖不变时无需重建）──────────────────────────────
# 构建命令：
#   docker build -f infra/docker/backend-base.dockerfile \
#                -t lianleme-base:latest backend/
#
# 仅在 pyproject.toml 或 uv.lock 变更时重新执行此构建。

# ── Stage 1: 编译依赖（builder）──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# 换清华 apt 源，加速国内下载
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources

# 安装编译时依赖（gcc/libpq-dev 仅在此阶段使用，不进入最终镜像）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 只复制依赖描述文件，利用 Docker 层缓存
COPY pyproject.toml uv.lock ./

# 用 uv 导出锁定依赖并安装到 /install（pip/uv 使用清华 PyPI 镜像）
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uv \
    && uv export --frozen --no-dev --no-hashes -o requirements.txt \
    && pip install --no-cache-dir --prefix=/install \
       -i https://pypi.tuna.tsinghua.edu.cn/simple \
       -r requirements.txt \
    && rm requirements.txt


# ── Stage 2: 基础运行镜像（base）─────────────────────────────────────────────
FROM python:3.11-slim AS base

WORKDIR /app

# 换清华 apt 源，加速国内下载
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources

# 仅安装运行时必需的系统库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 拷贝已安装的 Python 包
COPY --from=builder /install /usr/local

# 创建非 root 用户，降低容器权限
RUN groupadd -r appuser && useradd -r -g appuser appuser

EXPOSE 8000
