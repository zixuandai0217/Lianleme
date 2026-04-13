#!/usr/bin/env bash
# 功能：构建后端基础镜像（lianleme-base:latest），用于缓存 Python 依赖层。
# 参数：无。
# 示例：
#   bash scripis/build-base.sh
# 说明：通常仅在依赖变更（如 pyproject.toml / lock 文件更新）时执行。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DOCKER_DIR="${REPO_ROOT}/infra/docker"
BACKEND_DIR="${REPO_ROOT}/backend"

IMAGE_NAME="lianleme-base:latest"

echo "=============================="
echo "  构建基础镜像: ${IMAGE_NAME}"
echo "  context   : ${BACKEND_DIR}"
echo "  dockerfile: ${DOCKER_DIR}/backend-base.dockerfile"
echo "=============================="

docker build \
  --file "${DOCKER_DIR}/backend-base.dockerfile" \
  --tag  "${IMAGE_NAME}" \
  "${BACKEND_DIR}"

echo ""
echo "✓ 基础镜像构建完成: ${IMAGE_NAME}"
