#!/usr/bin/env bash
# 停止开发环境
# 用法：
#   bash dev-down.sh        # 停止容器（保留数据 volume）
#   bash dev-down.sh -v     # 停止容器并清除所有 volume（重置数据库等）

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
