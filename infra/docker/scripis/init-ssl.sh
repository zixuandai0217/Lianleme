#!/usr/bin/env bash
# 功能：首次申请 Let's Encrypt 证书并写入 certbot 目录。
# 参数：
#   $1 证书通知邮箱（可选，优先级高于 .env），例如 your-email@example.com。
# 环境变量：
#   SSL_CERTBOT_EMAIL（写在 infra/docker/.env 中）
# 示例：
#   bash scripis/init-ssl.sh
#   bash scripis/init-ssl.sh your-email@example.com
# 说明：
#   - 会临时创建 nginx ACME 配置并启动 deploy compose 的 acme profile。
#   - 如检测到正式 nginx 在运行，会先暂停，申请完成后再恢复。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DOCKER_DIR="${REPO_ROOT}/infra/docker"
COMPOSE="docker compose -f ${DOCKER_DIR}/docker-compose.deploy.yml"

# 加载 Docker 环境变量（包含 SSL_CERTBOT_EMAIL）
if [ -f "${DOCKER_DIR}/.env" ]; then
  set -a
  source "${DOCKER_DIR}/.env"
  set +a
fi

DEFAULT_EMAIL="dzx0217@qq.com"
EMAIL="${1:-${SSL_CERTBOT_EMAIL:-${DEFAULT_EMAIL}}}"
DOMAIN="lianleme.cloud"

if [ -z "${EMAIL}" ]; then
  echo "用法：$0 [your-email@example.com]"
  echo "或在 ${DOCKER_DIR}/.env 中设置 SSL_CERTBOT_EMAIL"
  exit 1
fi

mkdir -p "${DOCKER_DIR}/nginx/certbot/conf"
mkdir -p "${DOCKER_DIR}/nginx/certbot/www"

echo "[1/3] 创建临时 Nginx 配置（仅用于证书申请）..."
cat > "${DOCKER_DIR}/nginx/nginx-temp.conf" << 'EOF'
server {
    listen 80;
    server_name lianleme.cloud www.lianleme.cloud;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
        allow all;
        default_type "text/plain";
    }

    location / {
        return 200 "练了么 AI 健身教练 - HTTPS 即将启用";
    }
}
EOF

echo "[2/3] 启动临时 Nginx（deploy compose 的 acme profile）..."
if ${COMPOSE} ps --services --status running | grep -qx "nginx"; then
  echo "检测到部署 nginx 正在运行，先临时停止..."
  ${COMPOSE} stop nginx
fi

${COMPOSE} --profile acme up -d nginx-acme
sleep 3

echo "[3/3] 申请 SSL 证书..."
docker run --rm \
  -v "${DOCKER_DIR}/nginx/certbot/conf:/etc/letsencrypt" \
  -v "${DOCKER_DIR}/nginx/certbot/www:/var/www/certbot" \
  certbot/certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email "${EMAIL}" \
  --agree-tos \
  --no-eff-email \
  --force-renewal \
  -d "${DOMAIN}" \
  -d "www.${DOMAIN}"

rm -f "${DOCKER_DIR}/nginx/nginx-temp.conf"
${COMPOSE} --profile acme stop nginx-acme >/dev/null 2>&1 || true
${COMPOSE} --profile acme rm -f nginx-acme >/dev/null 2>&1 || true

if ${COMPOSE} ps --services --status exited | grep -qx "nginx"; then
  echo "恢复部署 nginx..."
  ${COMPOSE} start nginx
fi

echo ""
echo "✓ SSL 证书申请成功！"
echo "  证书位置：${DOCKER_DIR}/nginx/certbot/conf/live/${DOMAIN}/"
