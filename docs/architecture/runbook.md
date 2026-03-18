# Why: 一页式运行手册，减少1-2人团队的环境切换成本。
# Scope: 本地启动、测试、前端构建、后端联调。
# Verify: 按步骤复制命令即可拉起全部核心服务。

## 1. 安装前端依赖

```bash
npm install --workspace apps/mobile-client --legacy-peer-deps
npm install --workspace apps/admin-console --legacy-peer-deps
```

## 2. 启动后端服务（四个终端）

```bash
cd services/profile-service && uv run python -m app.main
cd services/ai-coach-service && uv run python -m app.main
cd services/task-service && uv run python -m app.main
cd services/api-gateway && uv run python -m app.main
```

## 3. 启动前端

```bash
npm run dev:mobile:h5
npm run dev:admin
```

## 4. 运行测试

```bash
cd services/api-gateway && uv run --with pytest pytest -q
cd services/profile-service && uv run --with pytest pytest -q
cd services/ai-coach-service && uv run --with pytest pytest -q
cd services/task-service && uv run --with pytest pytest -q
```