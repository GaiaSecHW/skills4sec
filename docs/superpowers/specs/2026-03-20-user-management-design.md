# 用户管理模块设计文档

> 创建日期：2026-03-20
> 状态：待实现
> 版本：v1.1（根据审查反馈修订）

## 1. 概述

为 SkillHub 系统设计用户管理模块，实现基于工号 + API 密钥的认证方式，支持管理员后台管理用户。

### 1.1 核心需求

- 超级管理员通过 .env 配置，无公开注册功能
- 用户使用工号 + API 密钥登录
- 三层角色权限：super_admin > admin > user
- 完整的登录日志记录
- 管理后台支持用户 CRUD、批量导入导出

### 1.2 技术方案

采用**渐进式改造**方案，基于现有 backend 项目（Tortoise ORM + SQLite/MySQL）：
- 修改现有 User 模型字段
- 复用现有 Role 表机制
- 修改认证逻辑
- 新增管理后台 API
- 在现有 SPA 架构中添加管理页面路由

---

## 2. 数据库设计（Tortoise ORM）

### 2.1 User 模型（修改现有）

```python
# backend/app/models/user.py
from tortoise import fields
from tortoise.models import Model


class User(Model):
    """用户模型 - 基于工号+API密钥认证"""
    id = fields.IntField(pk=True)
    employee_id = fields.CharField(max_length=20, unique=True, index=True, description="工号")
    api_key_hash = fields.CharField(max_length=255, description="API密钥(bcrypt哈希)")
    name = fields.CharField(max_length=100, null=True, description="姓名")
    role = fields.CharField(max_length=20, default="user", description="角色: super_admin/admin/user")
    status = fields.CharField(max_length=20, default="active", description="状态: active/disabled")
    department = fields.CharField(max_length=100, null=True, description="部门")
    team = fields.CharField(max_length=100, null=True, description="团队")
    group_name = fields.CharField(max_length=100, null=True, description="分组")
    skills_count = fields.IntField(default=0, description="上传技能数")
    is_active = fields.BooleanField(default=True)  # 兼容现有字段
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    last_login = fields.DatetimeField(null=True, description="最后登录时间")

    class Meta:
        table = "users"
        indexes = [
            ("employee_id",),
            ("status", "role"),  # 复合索引优化列表查询
        ]

    def __str__(self):
        return f"{self.employee_id} - {self.name}"


# 保留现有 Role 和 UserRole 模型用于细粒度权限扩展
```

### 2.2 LoginLog 模型（新增）

```python
# backend/app/models/login_log.py
from tortoise import fields
from tortoise.models import Model


class LoginLog(Model):
    """登录日志模型"""
    id = fields.IntField(pk=True)
    employee_id = fields.CharField(max_length=20, index=True, description="工号")
    login_time = fields.DatetimeField(auto_now_add=True)
    status = fields.CharField(max_length=20, description="状态: success/failed")
    ip_address = fields.CharField(max_length=45, null=True, description="IP地址")
    user_agent = fields.CharField(max_length=500, null=True, description="浏览器信息")
    device_id = fields.CharField(max_length=100, null=True, description="设备标识")
    failure_reason = fields.CharField(max_length=100, null=True, description="失败原因")

    class Meta:
        table = "login_logs"
        indexes = [
            ("employee_id",),
            ("login_time",),
            ("status",),
        ]
```

### 2.3 AdminLog 模型（新增 - 操作审计）

```python
# backend/app/models/admin_log.py
from tortoise import fields
from tortoise.models import Model


class AdminLog(Model):
    """管理员操作日志模型"""
    id = fields.IntField(pk=True)
    admin_id = fields.IntField(index=True, description="操作者用户ID")
    admin_employee_id = fields.CharField(max_length=20, description="操作者工号")
    action = fields.CharField(max_length=50, description="操作类型: reset_key/delete_user/toggle_status等")
    target_user_id = fields.IntField(null=True, description="目标用户ID")
    target_employee_id = fields.CharField(max_length=20, null=True, description="目标用户工号")
    details = fields.JSONField(null=True, description="操作详情")
    ip_address = fields.CharField(max_length=45, null=True, description="IP地址")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "admin_logs"
        indexes = [
            ("admin_id",),
            ("action",),
            ("created_at",),
        ]
```

### 2.4 数据迁移方案

```python
# backend/app/migrations/user_migration.py
"""
用户数据迁移脚本
执行时机：部署新版本前

迁移步骤：
1. 添加新字段到 users 表
2. 将现有 username 映射到 employee_id
3. 将现有 hashed_password 映射到 api_key_hash
4. 设置默认角色
"""

async def migrate_users():
    from tortoise import Tortoise
    from tortoise.connection import connections

    conn = connections.get("default")

    # SQLite 语法
    # 1. 添加新列（如果不存在）
    await conn.execute_query(
        "ALTER TABLE users ADD COLUMN employee_id VARCHAR(20)"
    )
    await conn.execute_query(
        "ALTER TABLE users ADD COLUMN api_key_hash VARCHAR(255)"
    )
    await conn.execute_query(
        "ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user'"
    )

    # 2. 迁移数据
    await conn.execute_query(
        "UPDATE users SET employee_id = username WHERE employee_id IS NULL"
    )
    await conn.execute_query(
        "UPDATE users SET api_key_hash = hashed_password WHERE api_key_hash IS NULL"
    )
    await conn.execute_query(
        "UPDATE users SET role = 'admin' WHERE is_superuser = 1"
    )

    # 3. 创建唯一索引
    await conn.execute_query(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_employee_id ON users(employee_id)"
    )
```

---

## 3. API 设计

### 3.1 认证相关 `/api/auth`

| 端点 | 方法 | 权限 | 描述 |
|------|------|------|------|
| `/login` | POST | 公开 | 工号 + API 密钥登录 |
| `/logout` | POST | 登录 | 退出登录 |
| `/me` | GET | 登录 | 获取当前用户信息 |
| `/me/api-key` | PUT | 登录 | 修改自己的 API 密钥 |

**登录请求体：**
```json
{
    "employee_id": "w00000001",
    "api_key": "your-api-key"
}
```

**登录响应：**
```json
{
    "success": true,
    "access_token": "jwt-access-token",
    "refresh_token": "jwt-refresh-token",
    "token_type": "bearer",
    "expires_in": 1800,
    "user": {
        "id": 1,
        "employee_id": "w00000001",
        "name": "张三",
        "role": "admin"
    }
}
```

**HTTP 状态码：**
- 200: 成功
- 401: 认证失败（工号或密钥错误）
- 429: 请求过于频繁（触发限流）

### 3.2 用户管理 `/api/admin/users`（admin/super_admin）

| 端点 | 方法 | 描述 |
|------|------|------|
| `/` | GET | 用户列表 |
| `/` | POST | 新增用户 |
| `/{id}` | GET | 获取用户详情 |
| `/{id}` | PUT | 编辑用户 |
| `/{id}` | DELETE | 删除用户 |
| `/{id}/reset-key` | POST | 重置用户 API 密钥 |
| `/{id}/toggle-status` | POST | 切换启用/禁用状态 |
| `/import` | POST | 批量导入用户（CSV） |
| `/export` | GET | 导出用户列表（CSV） |

**用户列表查询参数（保持与现有 API 一致）：**
- `skip`: 偏移量（默认 0）
- `limit`: 每页数量（默认 20，最大 100）
- `employee_id`: 工号筛选
- `name`: 姓名筛选（模糊）
- `role`: 角色筛选
- `status`: 状态筛选

**批量导入参数：**
- `conflict_strategy`: 冲突处理策略（skip 跳过 / overwrite 覆盖 / raise 报错，默认 skip）
- `validate_only`: 仅验证不导入（boolean，默认 false）

**HTTP 状态码：**
- 200: 成功
- 401: 未认证
- 403: 权限不足
- 404: 用户不存在
- 409: 工号冲突（conflict_strategy=raise 时）
- 422: 参数验证失败

### 3.3 登录日志 `/api/admin/login-logs`（admin/super_admin）

| 端点 | 方法 | 描述 |
|------|------|------|
| `/` | GET | 日志列表 |

**查询参数：**
- `skip`: 偏移量
- `limit`: 每页数量
- `employee_id`: 工号筛选
- `status`: 登录状态筛选（success/failed）
- `start_date`: 开始日期（ISO 格式）
- `end_date`: 结束日期（ISO 格式）

### 3.4 操作日志 `/api/admin/admin-logs`（super_admin）

| 端点 | 方法 | 描述 |
|------|------|------|
| `/` | GET | 操作日志列表 |

---

## 4. 前端设计（SPA 架构）

### 4.1 登录页面改造

在现有登录框上方增加提示信息：

```
💡 请输入您的工号和 API 密钥登录系统
   如需账号，请联系管理员
```

表单字段：
- 工号（employee_id）
- API 密钥（api_key，密码类型输入框）

### 4.2 管理后台路由（在 app.js 中添加）

```javascript
// 路由配置
const routes = {
    // ... 现有路由
    'admin/users': renderAdminUsers,
    'admin/logs': renderAdminLogs,
};

// 管理后台入口（仅 admin/super_admin 可见）
function renderAdminNav() {
    return `
        <nav class="admin-nav">
            <a href="#admin/users" class="nav-item">用户管理</a>
            <a href="#admin/logs" class="nav-item">登录日志</a>
        </nav>
    `;
}
```

### 4.3 用户管理页面功能

- 搜索筛选（工号、姓名、状态）
- 新增用户按钮
- 批量导入按钮
- 导出按钮
- 用户列表表格（分页）
- 行操作：编辑、启用/禁用、删除

### 4.4 用户新增/编辑弹窗字段

- 工号（必填，编辑时只读）
- 姓名（必填）
- API 密钥（新增时必填，编辑时可选留空则不修改）
- 角色（下拉选择）
- 部门
- 团队
- 分组
- 状态

### 4.5 批量导入格式（CSV）

```csv
employee_id,name,api_key,role,department,team,group_name
w00000001,张三,xxx-api-key-32chars-min,admin,研发部,后端组,A组
w00000002,李四,yyy-api-key-32chars-min,user,测试部,测试组,B组
```

**导入要求：**
- 编码：UTF-8
- 第一行为表头
- api_key 长度至少 32 字符

---

## 5. 配置与安全

### 5.1 环境变量配置

```env
# 超级管理员配置
SUPER_ADMIN_EMPLOYEE_ID=w00000001
SUPER_ADMIN_API_KEY=your-secure-api-key-min-32-chars
SUPER_ADMIN_NAME=系统管理员

# JWT 安全配置
SECRET_KEY=your-jwt-secret-key-random-string
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# API 密钥要求
API_KEY_MIN_LENGTH=32

# 登录安全
MAX_LOGIN_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=30
```

### 5.2 安全措施

| 措施 | 说明 |
|------|------|
| API 密钥加密 | 使用 bcrypt 哈希存储，不明文保存 |
| Access Token | 短期有效（30 分钟），用于 API 认证 |
| Refresh Token | 长期有效（7 天），用于刷新 Access Token |
| 登录限流 | 同一 IP 5 次失败后锁定 30 分钟（内存存储，单实例） |
| 操作审计 | 管理员操作记录到 admin_logs 表 |
| 权限校验 | 每个接口验证角色权限 |

### 5.3 API 密钥验证规则

```python
import re

def validate_api_key(api_key: str) -> tuple[bool, str]:
    """验证 API 密钥复杂度"""
    if len(api_key) < 32:
        return False, "API 密钥长度至少 32 字符"

    # 检查是否包含常见弱密钥模式
    weak_patterns = ['123456', 'password', 'admin', 'qwerty']
    for pattern in weak_patterns:
        if pattern.lower() in api_key.lower():
            return False, f"API 密钥不能包含常见弱密钥模式"

    return True, ""
```

### 5.4 权限矩阵

| 功能 | super_admin | admin | user |
|------|:-----------:|:-----:|:----:|
| 用户列表 | ✅ | ✅ | ❌ |
| 新增/编辑用户 | ✅ | ✅ | ❌ |
| 删除用户 | ✅ | ✅ | ❌ |
| 查看登录日志 | ✅ | ✅ | ❌ |
| 查看操作日志 | ✅ | ❌ | ❌ |
| 重置用户密钥 | ✅ | ✅ | ❌ |
| 上传技能 | ✅ | ✅ | ✅ |
| 管理自己技能 | ✅ | ✅ | ✅ |

### 5.5 超级管理员初始化

系统启动时自动检查并创建超级管理员（在 `main.py` 的 `lifespan` 中执行）：

```python
async def init_super_admin():
    """初始化超级管理员"""
    from app.models.user import User
    from app.utils.security import hash_api_key
    from app.config import settings

    employee_id = settings.SUPER_ADMIN_EMPLOYEE_ID
    if not employee_id:
        return

    existing = await User.filter(employee_id=employee_id).first()
    if existing:
        # 更新密钥确保与 .env 一致
        existing.api_key_hash = hash_api_key(settings.SUPER_ADMIN_API_KEY)
        existing.role = "super_admin"
        await existing.save()
    else:
        # 创建超级管理员
        await User.create(
            employee_id=employee_id,
            api_key_hash=hash_api_key(settings.SUPER_ADMIN_API_KEY),
            name=settings.SUPER_ADMIN_NAME or "系统管理员",
            role="super_admin",
            status="active",
        )
```

---

## 6. 文件结构

```
backend/
├── app/
│   ├── models/
│   │   ├── user.py          # 修改：添加 employee_id/api_key_hash 等字段
│   │   ├── login_log.py     # 新增：登录日志模型
│   │   └── admin_log.py     # 新增：操作审计模型
│   ├── api/
│   │   ├── auth.py          # 修改：新的登录逻辑
│   │   └── admin.py         # 新增：管理后台 API
│   ├── schemas/
│   │   ├── user.py          # 修改：添加新字段 schema
│   │   └── log.py           # 新增：日志 schema
│   ├── utils/
│   │   └── security.py      # 修改：添加 API 密钥哈希/验证函数
│   ├── migrations/
│   │   └── user_migration.py # 新增：数据迁移脚本
│   └── config.py            # 修改：新增配置项
└── requirements.txt         # 无需修改（bcrypt/pyjwt 已存在）

docs/
└── assets/
    └── app.js               # 修改：添加管理后台路由和页面渲染
```

---

## 7. 实现优先级

### P0 - 核心功能（第 1 阶段）

- [ ] 修改 User 模型，添加新字段
- [ ] 创建 LoginLog、AdminLog 模型
- [ ] 修改 config.py 添加新配置项
- [ ] 修改 security.py 添加 API 密钥哈希函数
- [ ] 修改登录接口逻辑
- [ ] 超级管理员初始化
- [ ] 数据迁移脚本

### P1 - 管理功能（第 2 阶段）

- [ ] 用户管理 API（列表/新增/编辑/删除）
- [ ] 登录日志 API
- [ ] 操作审计日志 API
- [ ] 前端登录页改造
- [ ] 前端管理后台页面

### P2 - 增强功能（第 3 阶段）

- [ ] 批量导入/导出
- [ ] 登录限流
- [ ] API 密钥重置
- [ ] Refresh Token 刷新机制

---

## 8. 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-03-20 | 初始版本 |
| v1.1 | 2026-03-20 | 根据审查反馈修订：适配 Tortoise ORM、缩短 JWT 有效期、添加操作审计、修正前端 SPA 架构、统一 API 风格 |
