# VibeFit - AI 科学减肥健身应用

> 基于 FastAPI + uni-app 的科学减肥健身平台

## 🌟 项目简介

VibeFit 是一款面向大众的科学减肥健身应用，通过 AI 技术为用户提供个性化的饮食计划和运动训练方案。

### 核心功能

- 🍽️ **个性化饮食计划** - AI 根据您的身体数据和目标生成专属饮食方案
- 💪 **科学运动训练** - 定制化训练计划，适合居家和专业健身房
- 📊 **身体数据追踪** - 记录体重、体脂等数据，可视化趋势分析
- 🤖 **AI 健康顾问** - 7x24 小时在线解答减肥健身问题

## 🛠️ 技术栈

### 后端
- **框架**: FastAPI (Python 3.11+)
- **数据库**: PostgreSQL 15
- **ORM**: SQLAlchemy (异步)
- **认证**: JWT
- **AI 服务**: 通义千问

### 前端
- **框架**: uni-app + Vue 3
- **UI 组件**: uView UI
- **状态管理**: Pinia
- **目标平台**: 微信小程序、H5、App

### 部署
- **容器化**: Docker + Docker Compose
- **反向代理**: Nginx

## 📁 项目结构

```
VibeFit/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/               # API 路由
│   │   ├── core/              # 核心功能（AI、安全、计算器）
│   │   ├── models/            # 数据模型
│   │   ├── schemas/           # Pydantic 模式
│   │   ├── utils/             # 工具函数
│   │   ├── config.py          # 配置管理
│   │   ├── database.py        # 数据库连接
│   │   └── main.py            # 应用入口
│   ├── pyproject.toml         # 项目配置（uv）
│   ├── requirements.txt       # Python 依赖
│   ├── Dockerfile             # Docker 配置
│   └── ENV_SETUP.md          # 环境配置说明
├── miniprogram/              # uni-app 前端
│   ├── pages/                # 页面
│   ├── api/                  # API 封装
│   ├── store/                # Pinia 状态管理
│   ├── utils/                # 工具函数
│   └── static/               # 静态资源
├── deploy/                   # 部署配置
│   └── nginx.conf           # Nginx 配置
├── docker-compose.yml       # Docker 编排
└── README.md                # 项目说明
```

## 🚀 快速开始

### 环境要求

- Python 3.11+
- PostgreSQL 15+
- Node.js 16+
- Docker & Docker Compose（可选）

### 方式一：Docker 部署（推荐）

```bash
# 1. 克隆项目
git clone <repo-url>
cd VibeFit

# 2. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，配置 AI API 密钥等

# 3. 启动服务
docker-compose up -d

# 4. 访问应用
# 前端：http://localhost
# 后端 API：http://localhost:8000
# API 文档：http://localhost:8000/docs
```

### 方式二：本地开发

#### 后端启动（使用 uv）

```bash
cd backend

# 1. 安装 uv（如果未安装）
# Windows PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 同步依赖（自动创建虚拟环境）
uv sync

# 3. 激活虚拟环境（可选）
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 5. 启动数据库（PostgreSQL）
# 确保 PostgreSQL 已安装并运行

# 6. 启动应用
uv run uvicorn app.main:app --reload
```

#### 添加依赖

```bash
# 添加生产依赖
uv add <package-name>

# 添加开发依赖
uv add --dev pytest
```

#### 前端启动

```bash
cd miniprogram

# 1. 安装依赖
npm install

# 2. 启动开发服务器（H5）
npm run dev:h5

# 3. 微信小程序
# 使用微信开发者工具导入项目
npm run dev:mp-weixin
```

## 📋 配置说明

### 后端配置（.env）

```bash
# 数据库
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/vibefit

# AI 服务（通义千问）
ALIYUN_API_KEY=your_api_key_here

# JWT 配置
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# 服务器
HOST=0.0.0.0
PORT=8000
DEBUG=True
```

### 获取 AI API 密钥

1. 访问 [阿里云百炼平台](https://bailian.console.aliyun.com/)
2. 注册/登录账号
3. 创建 API Key
4. 开通通义千问服务

## 📱 页面说明

| 页面 | 路径 | 说明 |
|------|------|------|
| 首页 | `/pages/index/index` | 数据概览、快捷操作 |
| 身体数据 | `/pages/profile/index` | 查看/录入身体数据 |
| 饮食计划 | `/pages/diet/index` | 今日饮食、饮食记录 |
| 运动训练 | `/pages/workout/index` | 训练计划、动作详情 |
| AI 顾问 | `/pages/chat/index` | AI 健康咨询 |
| 登录 | `/pages/login/index` | 手机号验证码登录 |

## 🔌 API 接口

后端提供 RESTful API，完整文档访问：`http://localhost:8000/docs`

### 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/auth/verify-code | 获取验证码 |
| POST | /api/v1/auth/login | 登录 |
| GET | /api/v1/profiles/current | 获取身体数据 |
| POST | /api/v1/profiles | 创建身体数据 |
| POST | /api/v1/diet/generate | 生成饮食计划 |
| POST | /api/v1/workout/generate | 生成运动计划 |
| POST | /api/v1/ai/chat | AI 对话 |
| GET | /api/v1/stats/summary | 汇总统计 |

## 🎨 UI 设计

### 配色方案

| 颜色 | 色值 | 用途 |
|------|------|------|
| 主色调（珊瑚橙） | `#FF8A65` | 按钮、强调色 |
| 辅助色（暖杏色） | `#FFCC80` | 卡片背景、进度条 |
| 成功色（清新绿） | `#81C784` | 完成状态 |
| 背景色（米白色） | `#FFF8E5` | 页面背景 |
| 文字色（暖棕色） | `#5D4037` | 主文字 |

## 📝 开发计划

- [ ] 食物拍照识别
- [ ] 动作视频演示
- [ ] 社交分享功能
- [ ] 数据导出功能
- [ ] 多语言支持

## ⚠️ 注意事项

1. 本项目仅供学习参考，不构成医疗建议
2. 如有健康问题请咨询专业医生或营养师
3. AI 生成的内容可能存在误差，请谨慎参考

## 📄 License

MIT License

## 👥 联系方式

如有问题或建议，欢迎提 Issue！
