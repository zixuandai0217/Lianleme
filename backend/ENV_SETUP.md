# VibeFit 后端环境管理

## 使用 uv 管理环境

[uv](https://github.com/astral-sh/uv) 是一个极速的 Python 包管理器，用于替代 pip 和 virtualenv。

### 安装 uv

```bash
# Windows PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 快速开始

```bash
cd backend

# 1. 创建虚拟环境并同步依赖
uv sync

# 2. 激活虚拟环境（可选，uv run 会自动使用）
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. 运行应用
uv run uvicorn app.main:app --reload
```

### 常用命令

```bash
# 同步依赖（创建/更新虚拟环境）
uv sync

# 添加开发依赖
uv sync --extra dev

# 添加新依赖
uv add <package-name>

# 添加开发依赖
uv add --dev <package-name>

# 移除依赖
uv remove <package-name>

# 运行应用
uv run uvicorn app.main:app --reload

# 运行脚本
uv run python scripts/xxx.py

# 查看依赖树
uv tree

# 检查过时的包
uv pip list --outdated

# 更新依赖锁定文件
uv lock --upgrade
```

### 项目结构

```
backend/
├── app/                    # 应用代码
├── pyproject.toml         # 项目配置
├── uv.lock                # 依赖锁定文件（自动生成）
├── .venv/                 # 虚拟环境（已忽略）
└── .env                   # 环境变量（已忽略）
```

### Docker 部署

使用 uv 的 Dockerfile：

```bash
docker-compose up -d
```

## 从 requirements.txt 迁移

如果你之前使用 requirements.txt：

```bash
# 初始化 pyproject.toml（如果还没有）
uv init --name vibefit-backend

# 从 requirements.txt 导入依赖
uv add $(cat requirements.txt)

# 之后可以删除 requirements.txt 或保留用于兼容
uv pip freeze > requirements.txt
```

## 优势

- 🚀 **极速** - 比 pip 快 10-100 倍
- 🔒 **可重复** - uv.lock 锁定依赖版本
- 🎯 **简单** - 一条命令完成环境创建和依赖安装
- 📦 **现代** - 支持 pyproject.toml 标准
- 🔗 **节省空间** - 全局缓存，硬链接共享
