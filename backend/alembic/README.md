# 缺失的文件已补充

## 已添加

### Alembic 数据库迁移
- `alembic/env.py` - 迁移环境配置
- `alembic/alembic.ini` - Alembic 配置文件
- `alembic/versions/README.md` - 迁移版本说明
- `alembic/versions/001_initial.py` - 初始迁移脚本（创建所有表）

## 使用方法

### 初始化数据库
```bash
cd backend

# 同步依赖
uv sync

# 激活环境
.venv\Scripts\activate  # Windows

# 运行迁移
uv run alembic upgrade head
```

### 创建新迁移
```bash
# 修改模型后生成新迁移
uv run alembic revision --autogenerate -m "add new column"

# 应用迁移
uv run alembic upgrade head
```

### 回滚迁移
```bash
# 回滚一步
uv run alembic downgrade -1

# 回滚到特定版本
uv run alembic downgrade <revision_id>
```
