# Issue tracker: Local markdown

Issues 以 markdown 文件形式存储在 `.scratch/<feature>/` 目录下。

## 工作流程

### 创建 issue

1. 在 `.scratch/` 下创建功能目录（如 `.scratch/auth-flow/`）
2. 在该目录下创建 `issue.md`，包含：
   - 标题（`# Issue: <title>`）
   - 描述
   - 任务清单
   - 相关文件链接

### Issue 状态

通过 frontmatter 标签管理状态：

```yaml
---
status: needs-triage | needs-info | ready-for-agent | ready-for-human | delivered | wontfix
delivered_in: <short-sha>   # 仅 delivered 时必填，记录交付提交
---
```

`delivered` 表示验收范围已实现并通过质量门；交付时把状态从 `ready-for-agent`
改为 `delivered`，并回填 `delivered_in` 提交号。

### 查找 issues

- 扫描 `.scratch/*/issue.md`
- 读取 frontmatter 提取状态
- 按状态过滤

## PRs 作为请求入口

**关闭**。外部 PRs 不会自动进入 triage 队列。
