#!/usr/bin/env bash
# 生产环境部署脚本
# 执行顺序：pull 第三方镜像 → down → up -d
# 用法：
#   bash deploy-prod.sh              # 仅重启服务（使用现有镜像）
#   bash deploy-prod.sh --build      # 重建后端镜像后再部署
#   bash deploy-prod.sh --build-base # 重建基础镜像 + 后端镜像后再部署

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DOCKER_DIR="${REPO_ROOT}/infra/docker"

COMPOSE="docker compose -f ${DOCKER_DIR}/docker-compose.prod.yml --env-file ${DOCKER_DIR}/.env"

# ── 解析参数 ──────────────────────────────────────────────────────────────────
BUILD_BASE=false
BUILD_BACKEND=false

for arg in "$@"; do
  case "${arg}" in
    --build-base) BUILD_BASE=true; BUILD_BACKEND=true ;;
    --build)      BUILD_BACKEND=true ;;
  esac
done

# ── Step 1: 按需重建镜像 ──────────────────────────────────────────────────────
if [ "${BUILD_BASE}" = true ]; then
  echo "[1/4] 重建基础镜像..."
  bash "${SCRIPT_DIR}/build-base.sh"
fi

if [ "${BUILD_BACKEND}" = true ]; then
  echo "[2/4] 重建后端镜像..."
  bash "${SCRIPT_DIR}/build-backend.sh"
else
  echo "[1/4] 跳过镜像构建（使用现有 lianleme-backend:latest）"
fi

# ── Step 2: 拉取第三方镜像（postgres / redis / minio）────────────────────────
echo ""
echo "[2/4] 拉取第三方镜像..."
${COMPOSE} pull postgres redis minio

# ── Step 3: 停止旧容器 ────────────────────────────────────────────────────────
echo ""
echo "[3/4] 停止旧容器..."
${COMPOSE} down --remove-orphans

# ── Step 4: 启动所有服务 ──────────────────────────────────────────────────────
echo ""
echo "[4/4] 启动服务..."
${COMPOSE} up -d

echo ""
echo "✓ 部署完成，当前运行状态："
${COMPOSE} ps
