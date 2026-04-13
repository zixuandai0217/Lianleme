#!/usr/bin/env bash
# 功能：构建后端应用镜像（lianleme-backend:latest）。
# 参数：无。
# 示例：
#   bash scripis/build-backend.sh
# 说明：依赖基础镜像 lianleme-base:latest，若不存在会直接报错退出。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DOCKER_DIR="${REPO_ROOT}/infra/docker"
BACKEND_DIR="${REPO_ROOT}/backend"

IMAGE_NAME="lianleme-backend:latest"

# 检查基础镜像是否存在
if ! docker image inspect lianleme-base:latest &>/dev/null; then
  echo "[ERROR] 基础镜像 lianleme-base:latest 不存在，请先执行 build-base.sh"
  exit 1
fi

echo "=============================="
echo "  构建后端镜像: ${IMAGE_NAME}"
echo "  context   : ${BACKEND_DIR}"
echo "  dockerfile: ${DOCKER_DIR}/backend.dockerfile"
echo "=============================="

docker build \
  --file "${DOCKER_DIR}/backend.dockerfile" \
  --tag  "${IMAGE_NAME}" \
  "${BACKEND_DIR}"

echo ""
echo "✓ 后端镜像构建完成: ${IMAGE_NAME}"
