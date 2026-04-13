#!/usr/bin/env bash
# 功能：停止开发环境。
# 参数：
#   -v, --volumes  停止并删除相关 volumes（会清空本地开发数据）。
# 示例：
#   bash scripis/dev-down.sh
#   bash scripis/dev-down.sh --volumes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DOCKER_DIR="${REPO_ROOT}/infra/docker"

COMPOSE="docker compose -f ${DOCKER_DIR}/docker-compose.yml --env-file ${DOCKER_DIR}/.env"

REMOVE_VOLUMES=false
for arg in "$@"; do
  case "${arg}" in
    -v|--volumes) REMOVE_VOLUMES=true ;;
  esac
done

if [ "${REMOVE_VOLUMES}" = true ]; then
  echo "停止开发环境并清除所有 volume（数据将被重置）..."
  ${COMPOSE} down -v --remove-orphans
  echo "✓ 开发环境已停止，volume 已清除"
else
  echo "停止开发环境（数据 volume 保留）..."
  ${COMPOSE} down --remove-orphans
  echo "✓ 开发环境已停止"
fi
