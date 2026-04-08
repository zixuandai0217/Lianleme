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

<!-- shift the local runbook URLs away from common defaults; startup reference only; verify each /health endpoint on the ports below -->
- Profile: `http://localhost:18010/health`
- AI Coach: `http://localhost:18020/health`
- Task: `http://localhost:18030/health`
- Gateway: `http://localhost:18000/health`

## 3. 启动前端

```bash
npm run dev:mobile:h5
npm run dev:admin
```

- Mobile H5: `http://localhost:5273`
- Admin Console: `http://localhost:5274`

## 4. 运行测试

```bash
cd services/api-gateway && uv run --with pytest pytest -q
cd services/profile-service && uv run --with pytest pytest -q
cd services/ai-coach-service && uv run --with pytest pytest -q
cd services/task-service && uv run --with pytest pytest -q
```
