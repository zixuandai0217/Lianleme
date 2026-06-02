# 练了么：上线版功能矩阵与两周排期

## 1. 目标

这份文档承接 [production-readiness-roadmap.md](/Users/edy/Daizixuan/Lianleme/docs/plans/2026-06-02-production-readiness-roadmap.md)，把“问题判断”进一步收敛为：

- 当前功能完成度矩阵
- P0 / P1 的任务清单
- 两周上线版排期建议
- 每项任务的验收标准与依赖关系

适用场景：

- 想尽快做一个可对真实用户开放的 MVP
- 想判断哪些功能该继续做，哪些先不要碰
- 想把现有代码从 demo 收敛成可交付产品

---

## 2. 功能完成度矩阵

| 模块 | 当前状态 | 已有能力 | 未完成点 | 上线优先级 |
|---|---|---|---|---|
| 认证登录 | 20% | JWT 生成、开发体验登录、微信登录后端接口雏形 | 无真正鉴权、无正式登录闭环、无 token 生命周期管理 | P0 |
| 用户档案 | 60% | 昵称、身高体重年龄目标经验可编辑 | 无字段校验策略、无首次建档引导、无越权保护 | P0 |
| 体型分析 | 55% | 图片上传、异步分析、轮询、历史记录、结果展示 | 任务是内存态、原图未资产化、无失败补偿 | P0 |
| 训练计划 | 65% | AI 生成周计划、周视图、今日训练读取 | 无计划解释、无版本对比、生成失败兜底过于粗糙 | P1 |
| 今日训练 / 打卡 | 70% | 今日训练展示、训练完成打卡、完成率记录、AI 反馈 | 训练过程状态弱、动作层级记录缺失、打卡反馈不够可解释 | P1 |
| AI 陪练 | 50% | 流式聊天、历史记录、训练上下文输入 | 输出契约不稳定、快捷动作硬编码、没有真正教练状态机 | P0 |
| 体重记录 | 75% | 记录、趋势图、删除、备注 | 无目标体重、无周期总结、无体重与训练联动洞察 | P1 |
| 管理后台 | 40% | 基础统计、用户分页列表 | `/admin/users` 未落地、无搜索筛选详情导出 | P1 |
| 推送提醒 | 25% | 微信订阅推送服务、定时任务代码雏形 | 未接入启动流程、模板 ID 占位、无用户订阅授权链路 | P1 |
| 对象存储 | 30% | MinIO 客户端、bucket 初始化、上传封装 | 主链路未使用、无签名 URL、无资源清理策略 | P0 |
| 工程质量 | 35% | TypeScript 类型检查通过、基础路由清晰 | lint 未通过、后端 0 测试、无 CI、无监控告警 | P0 |

---

## 3. 当前最短可交付产品链路

如果目标是“两周内尽快形成上线版”，建议只保留一条最短可交付链路：

1. 用户登录
2. 首次填写健身档案
3. 上传照片做体型分析
4. 自动生成周训练计划
5. 在首页看到今日训练
6. 训练中打开 AI 陪练
7. 训练后完成打卡
8. 每天记录体重并看到趋势
9. 定时收到训练提醒

任何不直接强化这条链路的能力，都应该延后。比如：

- 高级后台报表
- 多 provider 扩展
- 社交/社区
- 成就系统
- 饮食模块

这些都不是当前版本最应该做的事。

---

## 4. P0 任务清单

P0 的目标不是“更丰富”，而是“让它能够对真实用户开放”。

### P0-1 鉴权与权限收口

目标：

- 所有用户资源接口必须只允许访问当前登录用户自己的数据
- 管理接口必须显式校验管理员身份

涉及模块：

- [backend/app/api/user.py](/Users/edy/Daizixuan/Lianleme/backend/app/api/user.py)
- [backend/app/api/vision.py](/Users/edy/Daizixuan/Lianleme/backend/app/api/vision.py)
- [backend/app/api/plan.py](/Users/edy/Daizixuan/Lianleme/backend/app/api/plan.py)
- [backend/app/api/coach.py](/Users/edy/Daizixuan/Lianleme/backend/app/api/coach.py)
- [backend/app/api/workout.py](/Users/edy/Daizixuan/Lianleme/backend/app/api/workout.py)
- [backend/app/api/weight.py](/Users/edy/Daizixuan/Lianleme/backend/app/api/weight.py)

验收标准：

- 后端存在统一的 `get_current_user`
- 前端仅提交业务参数，不再把 `user_id` 当作可信身份
- 使用别人的 `user_id` 无法读取或改写其资源
- `dev-login` 在生产环境不可用

依赖：

- JWT 解码与异常处理
- 前端登录态恢复策略调整

### P0-2 正式登录接入

目标：

- 替换“快速体验登录”为正式用户可用的登录方式

当前建议：

- 如果正式形态是微信小程序：优先把微信登录链路接通
- 如果先交付 Web：增加短信验证码或统一 OAuth

验收标准：

- 登录页存在正式可用入口
- 新用户首次进入会自动建档
- 登录失败原因可感知
- 页面刷新后登录态可恢复

### P0-3 体型分析任务持久化

目标：

- 分析任务从内存字典迁移到数据库或任务队列

当前问题源头：

- [backend/app/api/vision.py](/Users/edy/Daizixuan/Lianleme/backend/app/api/vision.py) 的 `_tasks`

验收标准：

- 分析任务有单独持久记录
- 服务重启后任务状态不丢
- 失败任务可追踪
- 历史记录和任务状态分层清晰

### P0-4 对象存储接入主链路

目标：

- 用户上传图片不再只以 base64 在链路中流转

验收标准：

- 原图写入 MinIO
- DB 保存对象 key / URL
- 历史记录返回缩略图 URL 或签名 URL
- 图片大小、格式、分辨率有校验

### P0-5 AI 陪练输出协议收口

目标：

- 避免前端直接把模型原始输出当展示内容

推荐方案：

- 使用结构化 SSE 事件流，而不是裸文本 token

最低验收标准：

- 聊天气泡中不再出现 JSON/代码块泄漏
- 快捷动作来自服务端，而不是前端写死
- 异常输出可兜底

### P0-6 工程质量达标

目标：

- 建立最小上线质量门

必须完成：

- `npm run typecheck` 通过
- `npm run lint` 通过
- `pytest` 不再是 0 测试
- 有至少一条主链路 smoke test
- 接入基础 CI

建议覆盖：

- 鉴权
- 分析任务状态流转
- 训练计划生成兜底
- 训练打卡
- 体重记录

### P0-7 运行与观测

目标：

- 系统出问题时能追踪，不是“用户说坏了才知道”

验收标准：

- 结构化日志
- 请求链路错误日志
- 后台任务错误日志
- LLM 调用失败日志
- 基础健康检查与依赖检查

---

## 5. P1 任务清单

P1 的目标是让主链路从“能跑”升级到“像个产品”。

### P1-1 首次建档引导

目标：

- 用户登录后不需要自己摸索下一步

建议：

- 没填档案 -> 引导去个人资料
- 没做分析 -> 引导去体型分析
- 没有计划 -> 引导生成训练计划

验收标准：

- 首次使用流程清晰
- 用户知道自己当前缺哪一步

### P1-2 训练计划解释性增强

目标：

- 不只是给出“练什么”，还要说明“为什么这样练”

建议补充：

- 本周目标
- 重点肌群来源于哪次分析
- 动态调整说明
- 本周总训练量摘要

### P1-3 今日训练过程增强

目标：

- 从静态训练清单升级为可推进的训练过程页

建议补充：

- 当前动作
- 当前组数
- 完成进度
- 下一步动作建议
- 与 AI 陪练联动

### P1-4 打卡后的反馈闭环

目标：

- 用户打卡后能理解成果和变化

建议补充：

- 本次完成率
- 与上次相比
- AI 恢复建议
- 是否影响下周计划

### P1-5 体重趋势总结

目标：

- 体重记录不只是图表，而是可理解的趋势

建议补充：

- 7 天/30 天变化
- 阶段性最低/最高
- 与训练频率关联
- 是否偏离目标

### P1-6 提醒召回体系

目标：

- 用户不是只在打开应用时才被看见

建议补充：

- 每日训练提醒
- 连续多天未训练提醒
- 达成周目标提醒

前提依赖：

- 正式登录
- 用户订阅授权
- 后台任务可稳定运行

### P1-7 管理后台补齐

目标：

- 让后台真的可用于运营，而不仅是展示

建议补充：

- `/admin/users` 子路由与页面
- 搜索
- 筛选
- 用户详情页
- 导出
- 关键行为轨迹

---

## 6. 两周上线版排期建议

这里假设团队规模是 1 名前端 + 1 名后端，或你自己主导串行推进。

## 第 1 周：先解决系统性风险

### Day 1-2

- 鉴权设计收口
- 确定正式登录路径
- 明确前后端身份模型
- 补统一用户上下文依赖

交付物：

- 鉴权方案定稿
- 后端统一 current user 依赖

### Day 3-4

- 改造核心接口权限
- 移除生产环境对 `dev-login` 的依赖
- 前端认证恢复逻辑调整

交付物：

- 主链路接口完成权限收口
- 登录态恢复正常

### Day 5

- 体型分析任务持久化设计与落地
- 失败/超时状态补齐

交付物：

- 分析任务不再依赖进程内 `_tasks`

### Day 6

- 图片接入对象存储
- 分析历史返回资源引用

交付物：

- 图片主链路资产化

### Day 7

- AI 陪练协议修复
- 清理前端硬编码动作按钮
- 基础异常兜底

交付物：

- 陪练界面稳定展示

## 第 2 周：把主链路做成产品

### Day 8

- 首次建档引导
- 主链路引导逻辑

### Day 9

- 训练计划解释增强
- 今日训练页过程化增强

### Day 10

- 打卡后的反馈闭环
- 调整计划说明展示

### Day 11

- 体重趋势总结增强
- 与训练记录关联的轻量洞察

### Day 12

- 提醒系统接入启动流程
- 订阅授权链路打通

### Day 13

- 管理后台补齐最小可用能力
- `/admin/users` 落地

### Day 14

- 补测试
- 过 lint/typecheck/test
- 回归主链路
- 预发布检查

---

## 7. 每项任务完成的验收口径

为了避免“代码写了但产品没完成”，建议用下面的口径验收：

### 产品验收

- 用户是否知道下一步做什么
- 页面是否解释了当前状态
- AI 输出是否可被用户理解
- 用户是否能从一次训练后获得明确反馈

### 技术验收

- 接口是否有权限保护
- 是否可在重启后恢复任务状态
- 是否有日志与异常追踪
- 是否有自动化验证覆盖

### 运营验收

- 是否能知道用户做到了哪一步
- 是否有最小提醒能力
- 是否能在后台找到用户与异常数据

---

## 8. 不建议现在继续做的功能

这些功能不是没价值，而是不该抢在 P0/P1 前面：

- 饮食计划
- 课程体系
- 社区互动
- 成就系统
- 多模型 provider 策略扩展
- 高级数据驾驶舱

原因很简单：如果主链路还不稳，新增功能只会放大返工成本。

---

## 9. 最推荐的下一步

如果现在要立即开工，我建议按下面顺序推进：

1. 鉴权收口
2. 分析任务持久化
3. AI 陪练协议修复
4. 正式登录接入
5. 主链路引导与反馈增强

这个顺序的好处是：

- 先把风险最大的坑填掉
- 再把用户体验最核心的一条链路做顺
- 后面的提醒、后台、趋势增强才能站得住

---

## 10. 对应代码证据索引

认证与登录：

- [backend/app/api/user.py](/Users/edy/Daizixuan/Lianleme/backend/app/api/user.py)
- [backend/app/services/user/user_service.py](/Users/edy/Daizixuan/Lianleme/backend/app/services/user/user_service.py)
- [web/src/hooks/use-auth.ts](/Users/edy/Daizixuan/Lianleme/web/src/hooks/use-auth.ts)
- [web/src/pages/login/index.tsx](/Users/edy/Daizixuan/Lianleme/web/src/pages/login/index.tsx)

体型分析：

- [backend/app/api/vision.py](/Users/edy/Daizixuan/Lianleme/backend/app/api/vision.py)
- [backend/app/services/ai/vision_graph.py](/Users/edy/Daizixuan/Lianleme/backend/app/services/ai/vision_graph.py)
- [web/src/pages/analysis/index.tsx](/Users/edy/Daizixuan/Lianleme/web/src/pages/analysis/index.tsx)

训练计划与打卡：

- [backend/app/api/plan.py](/Users/edy/Daizixuan/Lianleme/backend/app/api/plan.py)
- [backend/app/services/plan/plan_service.py](/Users/edy/Daizixuan/Lianleme/backend/app/services/plan/plan_service.py)
- [backend/app/services/workout/workout_service.py](/Users/edy/Daizixuan/Lianleme/backend/app/services/workout/workout_service.py)
- [web/src/pages/plan/index.tsx](/Users/edy/Daizixuan/Lianleme/web/src/pages/plan/index.tsx)
- [web/src/pages/dashboard/index.tsx](/Users/edy/Daizixuan/Lianleme/web/src/pages/dashboard/index.tsx)

AI 陪练：

- [backend/app/api/coach.py](/Users/edy/Daizixuan/Lianleme/backend/app/api/coach.py)
- [backend/app/services/ai/coach_graph.py](/Users/edy/Daizixuan/Lianleme/backend/app/services/ai/coach_graph.py)
- [web/src/pages/coach/index.tsx](/Users/edy/Daizixuan/Lianleme/web/src/pages/coach/index.tsx)

体重记录：

- [backend/app/api/weight.py](/Users/edy/Daizixuan/Lianleme/backend/app/api/weight.py)
- [backend/app/services/weight/weight_service.py](/Users/edy/Daizixuan/Lianleme/backend/app/services/weight/weight_service.py)
- [web/src/pages/weight/index.tsx](/Users/edy/Daizixuan/Lianleme/web/src/pages/weight/index.tsx)

后台与提醒：

- [web/src/components/admin-layout.tsx](/Users/edy/Daizixuan/Lianleme/web/src/components/admin-layout.tsx)
- [web/src/pages/admin/index.tsx](/Users/edy/Daizixuan/Lianleme/web/src/pages/admin/index.tsx)
- [backend/app/services/push/push_service.py](/Users/edy/Daizixuan/Lianleme/backend/app/services/push/push_service.py)

对象存储与基础设施：

- [backend/app/core/storage.py](/Users/edy/Daizixuan/Lianleme/backend/app/core/storage.py)
- [backend/app/main.py](/Users/edy/Daizixuan/Lianleme/backend/app/main.py)
