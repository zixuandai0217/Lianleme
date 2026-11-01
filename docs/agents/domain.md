# Domain docs

## 布局

**单一上下文**：

- `CONTEXT.md` — 根目录，项目整体上下文
- `docs/adr/` — 架构决策记录（ADR）

## Consumer 规则

### 何时读取

- 开始新功能或重大重构前
- 不确定领域术语或设计意图时
- 需要理解架构决策的背景时

### 如何使用

1. **先读 `CONTEXT.md`** — 了解项目整体上下文、核心概念、术语表
2. **按需查阅 ADR** — 当遇到特定架构决策问题时，扫描 `docs/adr/` 中相关的决策记录
3. **保持同步** — 做出新的架构决策时，记录新的 ADR

### ADR 命名规范

```
docs/adr/
  0001-record-architecture-decisions.md
  0002-use-postgres-for-persistence.md
  0003-...
```

格式：`NNNN-kebab-case-title.md`
