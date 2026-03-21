# ToSet
<!-- config reminder doc; root-level manual setup checklist; verify by reviewing current service env vars and docker compose -->

这个文件只用于提醒后续需要手动补齐哪些运行配置，不存放任何真实密钥、密码、连接串或私有地址。

## 当前必须自行配置

- `api-gateway`
  - `PORT`
  - `PROFILE_SERVICE_BASE_URL`
  - `AI_COACH_SERVICE_BASE_URL`
  - `TASK_SERVICE_BASE_URL`
- `profile-service`
  - `PORT`
- `ai-coach-service`
  - `PORT`
  - `TEXT_MODEL`
  - `VISION_MODEL`
- `task-service`
  - `PORT`
  - `REDIS_URL`
- 前端本地联调
  - 需要保证网关可从 `http://localhost:8000` 访问
  - `apps/admin-console` 和 `apps/mobile-client` 本地开发时都会把 `/v1` 代理到这个地址

## 当前暂时不用配置

- `PostgreSQL / DATABASE_URL`
  - 当前仓库的 README 和 `docker-compose.yml` 提到了 PostgreSQL
  - 但现有代码还没有真实 SQL 读写、ORM、迁移或 `DATABASE_URL` 依赖
  - 所以它目前属于“文档/未来架构需要”，不是“当前 demo 运行必需”
- 真实 AI 供应商 `API_KEY / BASE_URL`
  - 当前 `ai-coach-service` 主要是本地规则 + LangGraph 编排
  - 还没有真实接入外部模型供应商接口
- `JWT_SECRET`
  - 当前登录态仍是内存态 token
  - 还不是正式鉴权系统必需的密钥配置

## 如果按接近生产环境准备

- 数据库相关
  - `DATABASE_URL`
  - 数据库账号、密码、库名
  - 迁移工具与迁移执行方式
- AI 能力相关
  - 模型供应商 `API_KEY`
  - 模型供应商 `BASE_URL`
  - 模型名映射、超时、重试等运行参数
- 文件与图片相关
  - 对象存储
  - CDN
- 部署与访问控制相关
  - 域名
  - CORS 白名单
  - HTTPS / 反向代理
- 账号体系相关
  - 短信验证码服务

## 使用说明

- 后续每次接入新的基础设施时，先更新这份 `ToSet.md`，再去补 `.env`、Docker、CI/CD 或部署平台中的实际配置。
