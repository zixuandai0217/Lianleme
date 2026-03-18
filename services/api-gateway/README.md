# api-gateway

对外统一 API 网关：
- 对客户端暴露 `/v1/*`
- 聚合 profile/ai/task 三个内部服务
- 注入 `trace_id` 并输出结构化日志