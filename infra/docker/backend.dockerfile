# ── App Image: 仅包含代码层（基于 lianleme-base）─────────────────────────────
# 构建命令：
#   docker build -f infra/docker/backend.dockerfile \
#                -t lianleme-backend:latest backend/
#
# 日常代码更新只需重建此镜像，秒级完成（依赖层来自 lianleme-base，已缓存）。
# 若依赖变更，先重建 backend-base.dockerfile，再重建此文件。

FROM lianleme-base:latest

# 拷贝应用代码（仅此层变动）
COPY --chown=appuser:appuser . .

USER appuser

# 生产环境：1 个 worker（适配 2核2G 服务器），关闭 reload
# 升级到 2核4G 后可将 --workers 改为 2
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
