# CI 与合并门禁

本地先跑 `python tools/quality_gate.py`，合并前跑 `python tools/quality_gate.py --full`；
报告制检查用 `python tools/quality_gate.py --report`。
工作流见 [ci.yml](../../.github/workflows/ci.yml)。推送、PR（含草稿）及手动运行都会触发；
同一工作流、同一分支/PR 的新提交会取消未完成的旧运行。

工单 01 / 02 的落地修订（前端类型检查空跑修复、必需检查 7 个、草稿不跳过、报告步骤归属门、
超时上限、缓存键规则）记录在 `.scratch/quality-gate-and-ci/issue.md` 的
「Implementation Decisions」一节。

## 必需检查（7 个）

| 阶段 | 稳定的 GitHub 状态检查名 | 执行规则 |
| --- | --- | --- |
| A | `web-typecheck`、`web-lint`、`web-unit`、`backend-lint`、`backend-unit` | 五个独立并行 job |
| B | `smoke`、`web-build` | 每个 job 都 needs 全部阶段 A，A 全绿后才运行 |
| C（报告制） | `backend-mypy-report`、`coach-assets-report` | `--report` 档 + `continue-on-error: true`，不被任何 job needs |

阶段 A/B/C 都调用 [质量门](../../tools/quality_gate.py) 的 `--step`（A：`--step`，
B：`--full --step`，C：`--report --step`），而不是在 YAML 里复制 npm / pytest 命令，
因此命令、跳过登记校验、失败摘要、超时与退出码都沿用同一个实现。
完整档独有的 `web-build` 也属于必需检查（见 issue.md 修订记录），所以必需检查是 7 个。
阶段 C 的错误会出现在日志里，但不改变整体结论，不应设为分支保护必需检查。

每一步都有超时上限（`StepSpec.timeout_seconds`）：`run_step` 超时即按失败处理并终止子进程
（exit 124），CI job 的 `timeout-minutes` 必须大于等于该上限，否则由契约判定失败。

工具链固定为 Linux runner、Node 22、Python 3.12。前端只用 `npm ci`；后端先 `test -f uv.lock`、
`uv lock --check` 校验锁文件存在且新鲜，再 `uv sync --frozen`。注意 `--frozen` 本身不检查锁
是否过期，所以不能省掉 `lock --check`。安装失败即失败，不使用 unlocked fallback。
npm 下载缓存与 uv 缓存分开，键只含 `runner.os` + 锁文件哈希，分支局部性交给 `restore-keys`；
不再使用 `github.ref`（per-branch 键永不命中）。

## 门 ⇔ CI 清单契约

[ci_contract.py](../../tools/ci_contract.py) 使用标准库读取工作流的受限 YAML 子集。
每个 job 必须标注 `# stage: A|B|C` 并有静态 `name`：

- 必需检查名在 `REQUIRED_CHECKS` 里钉死（7 个），并必须等于 `quality_gate.step_names("full")`；
  阶段 A 必须等于 `step_names("fast")`，阶段 B 等于完整档减去快速档。
- 报告制检查名必须等于 `step_names("report")`，且阶段 C job 必须 `continue-on-error: true`、
  不被任何 job `needs`。
- 每个必需 job 必须调用质量门同名 `--step`（不能自拼命令）、设 `timeout-minutes` 覆盖步骤上限、
  不得出现 `continue-on-error` / `if:` / `|| true`。
- 触发（push / pull_request）、`cancel-in-progress: true`、`npm ci`、`uv sync --frozen` +
  `uv lock --check` 缺失或写成 `npm install` / unfrozen 安装都会失败。

契约只用 `quality_gate.step_names` / `step_timeouts` 纯函数，不依赖 npm/uv，
所以没有前端工具链的环境也能跑。`backend-unit` 自动运行
[test_ci_contract.py](../../backend/tests/test_ci_contract.py)：本地快速门与 CI 走同一条
漂移检测路径。也可在根目录手动运行：

```sh
python tools/ci_contract.py --check
```

契约读取器不是通用 YAML 语法检查器；改变其支持的工作流结构时，应同时验证 YAML 语法
（本仓库验证方式：backend venv 里的 PyYAML `yaml.safe_load`，不作为运行时依赖）。

## GitHub 管理员必须配置的仓库设置

**分支保护不是代码，提交工作流不会自动配置 GitHub 的合并限制。** 管理员必须为受保护
目标分支启用「合并前要求状态检查通过」，逐字要求以下 7 个检查名（不加 `CI /` 前缀）：

```text
web-typecheck
web-lint
web-unit
backend-lint
backend-unit
smoke
web-build
```

不要要求两个 `*-report` 检查；不要以管理员绕过作为常规合并路径。完成设置后，任一必需检查
失败/未完成都会阻止合并。仓库内只能证明失败会非零退出以及编排不吞错；GitHub PR 上真实的
红色状态与拒绝合并，需要管理员配置后在远端运行验证。

**当前状态（2026-11-03）**：`main` 已按上表配置分支保护——7 个必需检查、
`strict: true`、禁止强推与删除；`enforce_admins: false`，单人仓库保留管理员直推的紧急通道，
常规路径仍应是「等 7 个检查全绿」。

## 无外部服务的 smoke 与故障金丝雀

[smoke](../../backend/tests/test_smoke_main_path.py) 使用临时 SQLite、真实路由与鉴权，
显式不启动 ASGI lifespan（避免真实 bucket/数据库初始化）；模型密钥清空，MinIO 客户端
访问被禁止，LLM 工厂替换为确定性反馈，打卡后的即发即弃调整任务被短路（它绑定生产全局会话，
且失败不可断言）。同一旅程不仅检查 200，还检查反馈标记：将 LLM 工厂替身改为抛错时，即使
应用兜底仍返回 200，成功路径也必须断言失败。负向测试捕获这一预期失败，并确认替身确实被调用。

## 门的负向金丝雀记录（工单 02，一次性人工动作）

只记录「怎么故意制造违规、跑了什么命令、观察到什么」，便于复现与审计。注入均为临时改动，
验证后已还原。

| # | 违规 | 命令 | 观察结果 |
| --- | --- | --- | --- |
| 1 | 前端类型错误：src 新增 `const canaryNotANumber: number = "boom";` | `python tools/quality_gate.py --step web-typecheck` | FAIL，exit 1，摘要含 `src/ci-canary.typecheck.ts(1,7): error TS2322`（还原后 PASS） |
| 2 | 前端 lint 违规：新增 `const unusedCanary = 1;` | `python tools/quality_gate.py --step web-lint` | FAIL，exit 1，`@typescript-eslint/no-unused-vars` |
| 3 | 单元断言失败：新增 `expect(1).toBe(2)` 的 vitest 用例 | `python tools/quality_gate.py --step web-unit` | FAIL，exit 1（1 failed） |
| 4 | smoke 断言失败：临时在 smoke 里加 `assert False` | `python tools/quality_gate.py --full --step smoke` | FAIL，exit 1，摘要 `FAIL smoke — ...::test_ci_canary_failure — assert False` |

**第 1 项曾暴露一个空跑缺陷（已修复）**：修复前 `web/package.json` 的 `typecheck` 是
`tsc --noEmit`，而 `web/tsconfig.json` 是 solution 风格（`files: []` + references），
`npx tsc --noEmit --listFilesOnly | grep -c src/` 为 `0`——一个文件都没检查，注入类型错误
也 PASS。现已改为 `tsc -b --force`（同时构建 app 与 node 两个 referenced project），并修掉
因此暴露的既有类型错误与两处配置问题（弃用的 `baseUrl`、`vite.config.ts` 的 `test` 字段
类型）；上表第 1 行是修复后重跑的真实红。详见 issue.md「工单 01 修订」。
