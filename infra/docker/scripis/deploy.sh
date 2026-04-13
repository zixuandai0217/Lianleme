#!/usr/bin/env bash
# 功能：部署生产环境服务（backend/postgres/redis/minio/nginx/certbot）。
# 参数：
#   --build         先重建后端镜像再部署。
#   --build-base    先重建基础镜像与后端镜像再部署。
#   --skip-ssl-init 跳过证书初始化检查（不建议首次部署使用）。
# 示例：
#   bash scripis/deploy.sh
#   bash scripis/deploy.sh --build
#   bash scripis/deploy.sh --build-base
#   bash scripis/deploy.sh --skip-ssl-init

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DOCKER_DIR="${REPO_ROOT}/infra/docker"

COMPOSE="docker compose -f ${DOCKER_DIR}/docker-compose.deploy.yml --env-file ${DOCKER_DIR}/.env"

BUILD_BASE=false
BUILD_BACKEND=false
SKIP_SSL_INIT=false

for arg in "$@"; do
  case "${arg}" in
    --build-base)    BUILD_BASE=true; BUILD_BACKEND=true ;;
    --build)         BUILD_BACKEND=true ;;
    --skip-ssl-init) SKIP_SSL_INIT=true ;;
    *)
      echo "未知参数：${arg}"
      echo "用法：$0 [--build] [--build-base] [--skip-ssl-init]"
      exit 1
      ;;
  esac
done

# 部署前自动检查证书：缺失则触发 init-ssl 初始化。
DOMAIN="lianleme.cloud"
CERT_DIR="${DOCKER_DIR}/nginx/certbot/conf/live/${DOMAIN}"
FULLCHAIN="${CERT_DIR}/fullchain.pem"
PRIVKEY="${CERT_DIR}/privkey.pem"

if [ "${SKIP_SSL_INIT}" = false ]; then
  if [ ! -f "${FULLCHAIN}" ] || [ ! -f "${PRIVKEY}" ]; then
    echo "[0/5] 检测到 SSL 证书缺失，自动执行 init-ssl.sh ..."
    bash "${SCRIPT_DIR}/init-ssl.sh"
  else
    echo "[0/5] 已检测到 SSL 证书，跳过初始化。"
  fi
else
  echo "[0/5] 已按参数跳过 SSL 初始化检查。"
fi

if [ "${BUILD_BASE}" = true ]; then
  echo "[1/5] 重建基础镜像..."
  bash "${SCRIPT_DIR}/build-base.sh"
fi

if [ "${BUILD_BACKEND}" = true ]; then
  echo "[2/5] 重建后端镜像..."
  bash "${SCRIPT_DIR}/build-backend.sh"
else
  echo "[1/5] 跳过镜像构建（使用现有 lianleme-backend:latest）"
fi

echo ""
echo "[3/5] 拉取第三方镜像..."
${COMPOSE} pull postgres redis minio nginx certbot

echo ""
echo "[4/5] 停止旧容器..."
${COMPOSE} down --remove-orphans

echo ""
echo "[5/5] 启动服务..."
${COMPOSE} up -d

echo ""
echo "✓ 部署完成，当前运行状态："
${COMPOSE} ps
