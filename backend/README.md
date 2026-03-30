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

---

## Docker 部署

### 架构

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Network                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────┐    ┌─────────────────────┐   │
│  │   nginx-container   │    │   backend-container  │   │
│  │                     │    │                     │   │
│  │  Nginx (HTTPS:443)  │───▶│  FastAPI (HTTP:8000) │   │
│  │                     │    │                     │   │
│  │  - 静态文件服务      │    │  - /api/* 路由      │   │
│  │  - /api 反向代理     │    │  - 管理后台静态文件  │   │
│  │  - SSL 终结          │    │                     │   │
│  └─────────────────────┘    └─────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 快速启动

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | `https://localhost` | 静态 SPA 站点 |
| API | `https://localhost/api/` | 后端 API |
| 管理后台 | `https://localhost/static/admin/` | 管理界面 |
| 后端直连 | `http://localhost:8000` | 直接访问后端（调试用） |

### 配置说明

#### 环境变量

复制 `.env.example` 为 `.env` 并配置：

```bash
cp .env.example .env
```

关键配置项：

```ini
# 数据库连接（支持 URL 编码特殊字符）
DATABASE_URL=mysql://root:password@localhost:3306/skills2

# 如果密码包含特殊字符（如 @），使用 URL 编码
# @ → %40
DATABASE_URL=mysql://root:Icsl%401234@localhost:3306/skills2

# JWT 配置
SECRET_KEY=your-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=360
```

#### SSL 证书

默认使用自签名证书，首次访问会有浏览器警告。生产环境建议替换为正式证书：

1. 将证书文件放到 `nginx/ssl/` 目录
2. 修改 `nginx/nginx.conf` 中的证书路径
3. 重新构建镜像

### 文件结构

```
├── backend/
│   ├── Dockerfile          # 后端容器
│   ├── .dockerignore       # Docker 忽略文件
│   └── ...
├── nginx/
│   ├── Dockerfile          # Nginx 容器
│   ├── nginx.conf          # Nginx 配置
│   └── generate-cert.sh    # 自签名证书生成脚本
├── docker-compose.yml      # 编排文件
└── docs/                   # 前端静态文件
```

### 故障排查

```bash
# 查看容器状态
docker ps -a

# 查看 Nginx 日志
docker logs skillhub-nginx

# 查看后端日志
docker logs skillhub-backend

# 进入容器调试
docker exec -it skillhub-backend sh
```

---

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
