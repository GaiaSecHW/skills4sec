# SecAgentHub Backend

FastAPI + Tortoise-ORM 后端服务

## 快速开始

### 1. 创建虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
.\venv\Scripts\activate  # Windows
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件配置数据库连接
```

### 4. 初始化数据库

```bash
# 初始化 Aerich 迁移
aerich init -t app.config.TORTOISE_ORM

# 生成初始迁移
aerich init-db

# 后续迁移
# aerich migrate --name "description"
# aerich upgrade
```

### 5. 运行开发服务器

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API 文档

启动服务后访问:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 项目结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置
│   ├── database.py          # 数据库初始化
│   │
│   ├── models/              # Tortoise-ORM 模型
│   │   ├── __init__.py
│   │   ├── enums.py         # 枚举定义
│   │   ├── user.py          # 用户模型
│   │   ├── skill.py         # 技能模型
│   │   ├── audit.py         # 安全审计模型
│   │   └── content.py       # 内容模型
│   │
│   ├── schemas/             # Pydantic 模型
│   │   ├── __init__.py
│   │   ├── skill.py
│   │   └── user.py
│   │
│   ├── api/                 # API 路由
│   │   ├── __init__.py
│   │   ├── skills.py
│   │   └── auth.py
│   │
│   ├── services/            # 业务逻辑
│   │   └── __init__.py
│   │
│   └── utils/               # 工具函数
│       ├── __init__.py
│       ├── pagination.py
│       └── security.py      # JWT + bcrypt
│
├── migrations/              # Aerich 迁移文件
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## API 端点

### 用户认证

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/auth/register` | 用户注册 | 公开 |
| POST | `/api/auth/login` | 用户登录 | 公开 |
| GET | `/api/auth/me` | 获取当前用户 | 认证 |
| PATCH | `/api/auth/me` | 更新当前用户 | 认证 |
| GET | `/api/auth/users` | 用户列表 | 管理员 |
| PATCH | `/api/auth/users/{id}/activate` | 启用用户 | 管理员 |
| PATCH | `/api/auth/users/{id}/deactivate` | 禁用用户 | 管理员 |

#### 认证示例

```bash
# 注册
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","email":"test@example.com","password":"test123"}'

# 登录获取 Token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}'
# 返回: {"access_token": "eyJ...", "token_type": "bearer"}

# 访问受保护的 API
curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer <token>"
```

### 技能管理

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/skills` | 获取技能列表 |
| POST | `/api/skills` | 创建技能 |
| GET | `/api/skills/{slug}` | 获取技能详情 |
| PATCH | `/api/skills/{slug}` | 更新技能 |
| DELETE | `/api/skills/{slug}` | 删除技能 |
| GET | `/api/skills/categories/list` | 获取分类列表 |
| GET | `/api/skills/tags/popular` | 获取热门标签 |

### 查询参数

`GET /api/skills` 支持以下查询参数:

- `page`: 页码 (默认 1)
- `page_size`: 每页数量 (默认 20, 最大 100)
- `category`: 按分类 slug 过滤
- `risk_level`: 按风险等级过滤 (safe/low/medium/high/critical)
- `tool`: 按支持工具过滤 (claude/codex/claude-code)
- `search`: 搜索关键词
- `source_type`: 按来源类型过滤 (official/community)

## 开发

### 运行测试

```bash
pytest
```

### 代码格式化

```bash
black app/
isort app/
```
