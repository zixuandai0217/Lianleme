#!/usr/bin/env bash
# 启动开发环境（热重载 + 代码挂载）
# 用法：
#   bash dev-up.sh           # 直接启动（使用现有镜像）
#   bash dev-up.sh --build   # 重建后端镜像后再启动
#   bash dev-up.sh --rebuild # 重建基础镜像 + 后端镜像后再启动

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DOCKER_DIR="${REPO_ROOT}/infra/docker"

COMPOSE="docker compose -f ${DOCKER_DIR}/docker-compose.yml --env-file ${DOCKER_DIR}/.env"

# ── 解析参数 ──────────────────────────────────────────────────────────────────
BUILD_BASE=false
BUILD_BACKEND=false

for arg in "$@"; do
  case "${arg}" in
    --rebuild) BUILD_BASE=true; BUILD_BACKEND=true ;;
    --build)   BUILD_BACKEND=true ;;
  esac
done

# ── 按需重建镜像 ──────────────────────────────────────────────────────────────
if [ "${BUILD_BASE}" = true ]; then
  echo "[1/2] 重建基础镜像..."
  bash "${SCRIPT_DIR}/build-base.sh"
fi

if [ "${BUILD_BACKEND}" = true ]; then
  echo "[2/2] 重建后端镜像..."
  bash "${SCRIPT_DIR}/build-backend.sh"
fi

# ── 启动开发环境 ───────────────────────────────────────────────────────────────
echo ""
echo "启动开发环境..."
${COMPOSE} up -d

echo ""
echo "✓ 开发环境已启动，当前状态："
${COMPOSE} ps
echo ""
echo "查看 API 日志：docker compose -f ${DOCKER_DIR}/docker-compose.yml logs -f api"
