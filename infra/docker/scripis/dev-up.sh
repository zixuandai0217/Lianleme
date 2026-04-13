#!/usr/bin/env bash
# 功能：启动本地开发环境（热重载 + 源码挂载）。
# 参数：
#   --build    先重建后端镜像再启动。
#   --rebuild  先重建基础镜像与后端镜像再启动。
# 示例：
#   bash scripis/dev-up.sh
#   bash scripis/dev-up.sh --build
#   bash scripis/dev-up.sh --rebuild

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DOCKER_DIR="${REPO_ROOT}/infra/docker"

COMPOSE="docker compose -f ${DOCKER_DIR}/docker-compose.yml --env-file ${DOCKER_DIR}/.env"

BUILD_BASE=false
BUILD_BACKEND=false

for arg in "$@"; do
  case "${arg}" in
    --rebuild) BUILD_BASE=true; BUILD_BACKEND=true ;;
    --build)   BUILD_BACKEND=true ;;
  esac
done

if [ "${BUILD_BASE}" = true ]; then
  echo "[1/2] 重建基础镜像..."
  bash "${SCRIPT_DIR}/build-base.sh"
fi

if [ "${BUILD_BACKEND}" = true ]; then
  echo "[2/2] 重建后端镜像..."
  bash "${SCRIPT_DIR}/build-backend.sh"
fi

echo ""
echo "启动开发环境..."
${COMPOSE} up -d

echo ""
echo "✓ 开发环境已启动，当前状态："
${COMPOSE} ps
