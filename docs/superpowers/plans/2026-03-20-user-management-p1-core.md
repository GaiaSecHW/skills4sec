# 用户管理模块 - P0 核心功能实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现基于工号+API密钥的认证系统，包括模型改造、安全工具函数、超级管理员初始化

**Architecture:** 修改现有 User 模型添加 employee_id/api_key_hash 字段，新增 LoginLog/AdminLog 模型，修改 auth.py 认证逻辑，在 lifespan 中初始化超级管理员

**Tech Stack:** FastAPI, Tortoise ORM, bcrypt, PyJWT (jose)

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/models/user.py` | 修改 | 添加 employee_id, api_key_hash, role, status 等字段 |
| `backend/app/models/login_log.py` | 新建 | 登录日志模型 |
| `backend/app/models/admin_log.py` | 新建 | 管理员操作日志模型 |
| `backend/app/models/__init__.py` | 修改 | 导出新模型 |
| `backend/app/config.py` | 修改 | 添加超级管理员和安全配置项 |
| `backend/app/utils/security.py` | 修改 | 添加 API 密钥哈希/验证函数 |
| `backend/app/schemas/user.py` | 修改 | 添加新字段 schema |
| `backend/app/schemas/log.py` | 新建 | 日志 schema |
| `backend/app/api/auth.py` | 修改 | 新登录逻辑 + refresh 端点 |
| `backend/app/database.py` | 修改 | 注册新模型 |

---

## Task 1: 修改配置文件

**Files:**
- Modify: `backend/app/config.py:1-50`

- [ ] **Step 1: 添加新配置项到 Settings 类**

在 `Settings` 类中添加以下配置项（在 `GITEA_REPO` 之后）：

```python
    # 超级管理员配置
    SUPER_ADMIN_EMPLOYEE_ID: str = ""
    SUPER_ADMIN_API_KEY: str = ""
    SUPER_ADMIN_NAME: str = "系统管理员"

    # API 密钥安全配置
    API_KEY_MIN_LENGTH: int = 32

    # 登录安全配置
    MAX_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 30

    # Refresh Token 配置
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
```

- [ ] **Step 2: 验证配置加载**

运行后端确认配置加载正常：
```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.config import settings; print(settings.API_KEY_MIN_LENGTH)"
```
Expected: `32`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(config): add user management config items

- Add super admin config (employee_id, api_key, name)
- Add API key security config (min_length)
- Add login security config (attempts, lockout)
- Add refresh token config (expire_days)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 修改 User 模型

**Files:**
- Modify: `backend/app/models/user.py:1-42`

- [ ] **Step 1: 添加新字段到 User 模型**

在 `User` 类中，在 `hashed_password` 之后添加新字段：

```python
class User(Model):
    """用户模型 - 基于工号+API密钥认证"""
    id = fields.IntField(pk=True)
    # 保留旧字段向后兼容
    username = fields.CharField(max_length=64, unique=True, index=True, null=True)
    email = fields.CharField(max_length=128, unique=True, index=True, null=True)
    hashed_password = fields.CharField(max_length=255, null=True)
    # 新增字段
    employee_id = fields.CharField(max_length=20, unique=True, index=True, description="工号")
    api_key_hash = fields.CharField(max_length=255, null=True, description="API密钥(bcrypt哈希)")
    name = fields.CharField(max_length=100, null=True, description="姓名")
    role = fields.CharField(max_length=20, default="user", description="角色: super_admin/admin/user")
    status = fields.CharField(max_length=20, default="active", description="状态: active/disabled")
    department = fields.CharField(max_length=100, null=True, description="部门")
    team = fields.CharField(max_length=100, null=True, description="团队")
    group_name = fields.CharField(max_length=100, null=True, description="分组")
    skills_count = fields.IntField(default=0, description="上传技能数")
    # 保留现有字段
    is_active = fields.BooleanField(default=True)
    is_superuser = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    last_login = fields.DatetimeField(null=True, description="最后登录时间")

    class Meta:
        table = "users"
        indexes = [
            ("employee_id",),
            ("status", "role"),
        ]

    def __str__(self):
        return f"{self.employee_id} - {self.name}"
```

- [ ] **Step 2: 验证模型语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.models.user import User; print('User model OK')"
```
Expected: `User model OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/user.py
git commit -m "feat(user-model): add employee_id and api_key_hash fields

- Add employee_id (unique, indexed) for work ID login
- Add api_key_hash for API key authentication
- Add role (super_admin/admin/user) and status (active/disabled)
- Add department, team, group_name, skills_count fields
- Add last_login timestamp
- Keep old username/email/hashed_password for compatibility

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 创建 LoginLog 模型

**Files:**
- Create: `backend/app/models/login_log.py`

- [ ] **Step 1: 创建登录日志模型**

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

    def __str__(self):
        return f"{self.employee_id} - {self.status} at {self.login_time}"
```

- [ ] **Step 2: 验证模型语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.models.login_log import LoginLog; print('LoginLog model OK')"
```
Expected: `LoginLog model OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/login_log.py
git commit -m "feat(models): add LoginLog model for login history

- Track login attempts with employee_id, status, ip_address
- Record user_agent and device_id for security auditing
- Add failure_reason for failed login analysis

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 创建 AdminLog 模型

**Files:**
- Create: `backend/app/models/admin_log.py`

- [ ] **Step 1: 创建管理员操作日志模型**

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

    def __str__(self):
        return f"{self.admin_employee_id} - {self.action}"
```

- [ ] **Step 2: 验证模型语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.models.admin_log import AdminLog; print('AdminLog model OK')"
```
Expected: `AdminLog model OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/admin_log.py
git commit -m "feat(models): add AdminLog model for admin operation auditing

- Track admin actions (reset_key, delete_user, toggle_status)
- Record target user info and operation details
- Add ip_address for security auditing

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: 更新模型导出和数据库注册

**Files:**
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/database.py`
- Modify: `backend/app/config.py` (TORTOISE_ORM)

- [ ] **Step 1: 更新 models/__init__.py**

```python
# backend/app/models/__init__.py
from app.models.user import User, Role, UserRole
from app.models.skill import Skill
from app.models.audit import AuditLog
from app.models.content import Content
from app.models.login_log import LoginLog
from app.models.admin_log import AdminLog

__all__ = [
    "User",
    "Role",
    "UserRole",
    "Skill",
    "AuditLog",
    "Content",
    "LoginLog",
    "AdminLog",
]
```

- [ ] **Step 2: 更新 database.py 注册新模型**

```python
# backend/app/database.py
from tortoise import Tortoise
from app.config import settings


async def init_db():
    await Tortoise.init(
        db_url=settings.DATABASE_URL,
        modules={
            "models": [
                "app.models.user",
                "app.models.skill",
                "app.models.audit",
                "app.models.content",
                "app.models.login_log",
                "app.models.admin_log",
            ]
        },
    )
    # 生成数据库表结构
    await Tortoise.generate_schemas()


async def close_db():
    await Tortoise.close_connections()
```

- [ ] **Step 3: 更新 config.py 中的 TORTOISE_ORM**

在 `config.py` 的 `TORTOISE_ORM` 配置中添加新模型：

```python
TORTOISE_ORM = {
    "connections": {"default": settings.DATABASE_URL},
    "apps": {
        "models": {
            "models": [
                "app.models.user",
                "app.models.skill",
                "app.models.audit",
                "app.models.content",
                "app.models.login_log",
                "app.models.admin_log",
            ],
            "default_connection": "default",
        }
    },
}
```

- [ ] **Step 4: 验证导入正常**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.models import LoginLog, AdminLog; print('Models import OK')"
```
Expected: `Models import OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/__init__.py backend/app/database.py backend/app/config.py
git commit -m "feat(models): register LoginLog and AdminLog in database

- Export new models in __init__.py
- Register models in database.py init
- Update TORTOISE_ORM config for aerich

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 添加 API 密钥安全函数

**Files:**
- Modify: `backend/app/utils/security.py:1-85`

- [ ] **Step 1: 添加 API 密钥哈希和验证函数**

在文件末尾添加：

```python
# ============ API 密钥相关函数 ============

def hash_api_key(api_key: str) -> str:
    """生成 API 密钥哈希（与密码哈希使用相同算法）"""
    return get_password_hash(api_key)


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """验证 API 密钥"""
    return verify_password(plain_key, hashed_key)


def validate_api_key_complexity(api_key: str) -> tuple[bool, str]:
    """验证 API 密钥复杂度"""
    import re

    if len(api_key) < 32:
        return False, "API 密钥长度至少 32 字符"

    # 检查是否包含常见弱密钥模式
    weak_patterns = ['123456', 'password', 'admin', 'qwerty', 'abcdef', '111111']
    api_key_lower = api_key.lower()
    for pattern in weak_patterns:
        if pattern in api_key_lower:
            return False, "API 密钥不能包含常见弱密钥模式"

    # 检查连续重复字符
    if re.search(r'(.)\1{3,}', api_key):
        return False, "API 密钥不能包含 4 个及以上连续相同字符"

    # 检查连续顺序字符
    if re.search(r'(0123|1234|2345|3456|4567|5678|6789|7890|abcd|bcde|cdef)', api_key_lower):
        return False, "API 密钥不能包含连续顺序字符"

    return True, ""
```

- [ ] **Step 2: 验证函数正常**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "
from app.utils.security import hash_api_key, verify_api_key, validate_api_key_complexity
hashed = hash_api_key('test-api-key-with-at-least-32-characters')
print('Hash OK:', len(hashed) > 50)
print('Verify OK:', verify_api_key('test-api-key-with-at-least-32-characters', hashed))
print('Validate short:', validate_api_key_complexity('short'))
print('Validate good:', validate_api_key_complexity('good-api-key-with-at-least-32-chars'))
"
```
Expected:
```
Hash OK: True
Verify OK: True
Validate short: (False, 'API 密钥长度至少 32 字符')
Validate good: (True, '')
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/utils/security.py
git commit -m "feat(security): add API key hash/verify and complexity validation

- Add hash_api_key() and verify_api_key() functions
- Add validate_api_key_complexity() for security checks
- Check length, weak patterns, repeated chars, sequential chars

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: 添加 JWT Refresh Token 支持

**Files:**
- Modify: `backend/app/utils/security.py`

- [ ] **Step 1: 添加 Refresh Token 创建函数**

在 `create_access_token` 函数后添加：

```python
def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT 刷新令牌"""
    to_encode = data.copy()
    to_encode.update({"type": "refresh"})  # 标记为 refresh token
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_refresh_token(token: str) -> Optional[str]:
    """验证刷新令牌，返回 employee_id 或 None"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return payload.get("sub")
    except JWTError:
        return None
```

- [ ] **Step 2: 验证函数正常**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "
from app.utils.security import create_refresh_token, verify_refresh_token
token = create_refresh_token({'sub': 'w00000001'})
employee_id = verify_refresh_token(token)
print('Refresh token created:', len(token) > 50)
print('Employee ID verified:', employee_id)
"
```
Expected:
```
Refresh token created: True
Employee ID verified: w00000001
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/utils/security.py
git commit -m "feat(security): add JWT refresh token support

- Add create_refresh_token() with 7-day expiry
- Add verify_refresh_token() for token validation
- Mark refresh tokens with type='refresh'

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: 添加权限校验依赖

**Files:**
- Modify: `backend/app/utils/security.py`

- [ ] **Step 1: 添加基于角色的权限校验函数**

在文件末尾添加：

```python
async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """获取当前管理员用户（admin 或 super_admin）"""
    if current_user.role not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要管理员权限"
        )
    return current_user


async def get_current_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """获取当前超级管理员"""
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要超级管理员权限"
        )
    return current_user
```

- [ ] **Step 2: 验证语法正确**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.utils.security import get_current_admin_user, get_current_super_admin; print('Permission deps OK')"
```
Expected: `Permission deps OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/utils/security.py
git commit -m "feat(security): add role-based permission dependencies

- Add get_current_admin_user() for admin/super_admin
- Add get_current_super_admin() for super_admin only

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 9: 更新用户 Schema

**Files:**
- Modify: `backend/app/schemas/user.py:1-52`

- [ ] **Step 1: 添加新的 Schema 类**

在文件末尾添加：

```python
# ============ 新增：工号登录相关 Schema ============

class UserLoginByEmployeeId(BaseModel):
    """工号+API密钥登录请求"""
    employee_id: str = Field(..., min_length=1, max_length=20, description="工号")
    api_key: str = Field(..., min_length=32, description="API密钥")


class UserCreateByAdmin(BaseModel):
    """管理员创建用户请求"""
    employee_id: str = Field(..., min_length=1, max_length=20, description="工号")
    name: str = Field(..., min_length=1, max_length=100, description="姓名")
    api_key: str = Field(..., min_length=32, description="API密钥")
    role: str = Field(default="user", pattern="^(user|admin|super_admin)$", description="角色")
    department: Optional[str] = Field(None, max_length=100, description="部门")
    team: Optional[str] = Field(None, max_length=100, description="团队")
    group_name: Optional[str] = Field(None, max_length=100, description="分组")


class UserUpdateByAdmin(BaseModel):
    """管理员更新用户请求"""
    name: Optional[str] = Field(None, max_length=100)
    api_key: Optional[str] = Field(None, min_length=32, description="留空则不修改")
    role: Optional[str] = Field(None, pattern="^(user|admin|super_admin)$")
    status: Optional[str] = Field(None, pattern="^(active|disabled)$")
    department: Optional[str] = Field(None, max_length=100)
    team: Optional[str] = Field(None, max_length=100)
    group_name: Optional[str] = Field(None, max_length=100)


class UserOutNew(BaseModel):
    """新用户输出（包含新字段）"""
    id: int
    employee_id: str
    name: Optional[str]
    role: str
    status: str
    department: Optional[str]
    team: Optional[str]
    group_name: Optional[str]
    skills_count: int
    last_login: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TokenWithRefresh(BaseModel):
    """带 Refresh Token 的响应"""
    success: bool = True
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # 30 minutes in seconds
    user: UserOutNew


class TokenRefresh(BaseModel):
    """刷新 Token 请求"""
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    """刷新 Token 响应"""
    success: bool = True
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1800
```

- [ ] **Step 2: 验证 Schema 语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.schemas.user import UserLoginByEmployeeId, TokenWithRefresh; print('Schema OK')"
```
Expected: `Schema OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/user.py
git commit -m "feat(schemas): add employee_id login and admin user schemas

- Add UserLoginByEmployeeId for new auth flow
- Add UserCreateByAdmin/UserUpdateByAdmin for admin operations
- Add UserOutNew with new fields
- Add TokenWithRefresh for JWT with refresh token

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 10: 创建日志 Schema

**Files:**
- Create: `backend/app/schemas/log.py`

- [ ] **Step 1: 创建日志 Schema 文件**

```python
# backend/app/schemas/log.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LoginLogOut(BaseModel):
    """登录日志输出"""
    id: int
    employee_id: str
    login_time: datetime
    status: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    device_id: Optional[str]
    failure_reason: Optional[str]

    class Config:
        from_attributes = True


class AdminLogOut(BaseModel):
    """管理员操作日志输出"""
    id: int
    admin_id: int
    admin_employee_id: str
    action: str
    target_user_id: Optional[int]
    target_employee_id: Optional[str]
    details: Optional[dict]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
```

- [ ] **Step 2: 验证 Schema 语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.schemas.log import LoginLogOut, AdminLogOut; print('Log schemas OK')"
```
Expected: `Log schemas OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/log.py
git commit -m "feat(schemas): add LoginLog and AdminLog output schemas

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 11: 修改认证 API - 新登录逻辑

**Files:**
- Modify: `backend/app/api/auth.py:1-179`

- [ ] **Step 1: 更新导入和添加新登录端点**

在文件顶部更新导入：

```python
from fastapi import APIRouter, HTTPException, status, Depends, Request
from datetime import timedelta, datetime

from app.models.user import User
from app.models.login_log import LoginLog
from app.schemas.user import (
    UserCreate, UserLogin, UserOut, UserUpdate, Token,
    UserLoginByEmployeeId, TokenWithRefresh, TokenRefresh,
    TokenRefreshResponse, UserOutNew
)
from app.utils.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    get_current_user,
    get_current_superuser,
    get_current_admin_user,
    verify_api_key,
    hash_api_key,
)
from app.config import settings
```

- [ ] **Step 2: 添加新登录端点**

在现有 `login` 函数后添加：

```python
@router.post("/login/new", response_model=TokenWithRefresh)
async def login_by_employee_id(
    request: Request,
    user_data: UserLoginByEmployeeId
):
    """
    工号 + API 密钥登录（新版）

    返回 JWT 访问令牌和刷新令牌。
    """
    # 获取客户端信息
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    # 查找用户
    user = await User.get_or_none(employee_id=user_data.employee_id)

    # 验证失败记录日志
    async def log_failure(reason: str):
        await LoginLog.create(
            employee_id=user_data.employee_id,
            status="failed",
            ip_address=client_ip,
            user_agent=user_agent,
            failure_reason=reason,
        )

    if not user:
        await log_failure("工号不存在")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="工号或 API 密钥错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.api_key_hash or not verify_api_key(user_data.api_key, user.api_key_hash):
        await log_failure("API 密钥错误")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="工号或 API 密钥错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != "active":
        await log_failure(f"用户状态异常: {user.status}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"用户已被{user.status}"
        )

    # 更新最后登录时间
    user.last_login = datetime.utcnow()
    await user.save()

    # 记录成功日志
    await LoginLog.create(
        employee_id=user.employee_id,
        status="success",
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # 创建令牌
    access_token = create_access_token(
        data={"sub": user.employee_id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_refresh_token(
        data={"sub": user.employee_id}
    )

    return TokenWithRefresh(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOutNew.model_validate(user),
    )
```

- [ ] **Step 3: 添加 Refresh Token 端点**

```python
@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(token_data: TokenRefresh):
    """
    刷新 Access Token

    使用有效的 Refresh Token 获取新的 Access Token。
    """
    employee_id = verify_refresh_token(token_data.refresh_token)
    if not employee_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 验证用户仍然有效
    user = await User.get_or_none(employee_id=employee_id)
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 创建新的 access token
    access_token = create_access_token(
        data={"sub": user.employee_id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return TokenRefreshResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
```

- [ ] **Step 4: 验证 API 语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.api.auth import router; print('Auth router OK')"
```
Expected: `Auth router OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py
git commit -m "feat(auth): add employee_id login and refresh token endpoints

- Add /login/new for employee_id + api_key authentication
- Add /refresh endpoint for access token refresh
- Record login attempts in LoginLog
- Return access_token + refresh_token in response

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 12: 超级管理员初始化

**Files:**
- Modify: `backend/app/main.py:1-62`

- [ ] **Step 1: 添加超级管理员初始化函数**

在 `lifespan` 函数之前添加：

```python
async def init_super_admin():
    """初始化超级管理员"""
    from app.models.user import User
    from app.utils.security import hash_api_key

    employee_id = settings.SUPER_ADMIN_EMPLOYEE_ID
    api_key = settings.SUPER_ADMIN_API_KEY

    if not employee_id or not api_key:
        return  # 未配置则跳过

    existing = await User.filter(employee_id=employee_id).first()
    if existing:
        # 更新密钥确保与 .env 一致
        existing.api_key_hash = hash_api_key(api_key)
        existing.role = "super_admin"
        existing.status = "active"
        await existing.save()
        print(f"[Init] 超级管理员已更新: {employee_id}")
    else:
        # 创建超级管理员
        await User.create(
            employee_id=employee_id,
            api_key_hash=hash_api_key(api_key),
            name=settings.SUPER_ADMIN_NAME or "系统管理员",
            role="super_admin",
            status="active",
        )
        print(f"[Init] 超级管理员已创建: {employee_id}")
```

- [ ] **Step 2: 在 lifespan 中调用初始化**

修改 `lifespan` 函数：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库
    await init_db()
    # 初始化超级管理员
    await init_super_admin()
    yield
    # 关闭时清理数据库连接
    await close_db()
```

- [ ] **Step 3: 添加导入**

确保文件顶部有必要的导入（`settings` 应该已经导入）：

```python
from app.config import settings
```

- [ ] **Step 4: 验证语法正确**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.main import app, init_super_admin; print('Main app OK')"
```
Expected: `Main app OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(main): add super admin initialization on startup

- Create super admin from .env config if not exists
- Update super admin credentials on startup
- Log initialization status

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 13: 删除旧数据库并测试

**Files:**
- None (测试任务)

- [ ] **Step 1: 备份并删除旧数据库**

```bash
cd D:/work/skillhub/skills4sec/backend
mv db.sqlite3 db.sqlite3.bak
rm -f db.sqlite3-shm db.sqlite3-wal
```

- [ ] **Step 2: 配置 .env 文件**

确保 `backend/.env` 包含超级管理员配置：

```env
SUPER_ADMIN_EMPLOYEE_ID=w00000001
SUPER_ADMIN_API_KEY=your-secure-api-key-at-least-32-characters-long!
SUPER_ADMIN_NAME=系统管理员
```

- [ ] **Step 3: 启动后端服务**

```bash
cd D:/work/skillhub/skills4sec/backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Expected output should include:
```
[Init] 超级管理员已创建: w00000001
INFO:     Uvicorn running on http://0.0.0.0:8001
```

- [ ] **Step 4: 测试登录 API**

```bash
curl -X POST http://localhost:8001/api/auth/login/new \
  -H "Content-Type: application/json" \
  -d '{"employee_id":"w00000001","api_key":"your-secure-api-key-at-least-32-characters-long!"}'
```

Expected: JSON response with `access_token`, `refresh_token`, and user info.

- [ ] **Step 5: 测试 Refresh Token**

使用上一步获取的 refresh_token：

```bash
curl -X POST http://localhost:8001/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<your-refresh-token>"}'
```

Expected: JSON response with new `access_token`.

---

## 验收标准

- [ ] User 模型包含 employee_id, api_key_hash, role, status 等新字段
- [ ] LoginLog 和 AdminLog 模型创建成功
- [ ] API 密钥哈希/验证函数正常工作
- [ ] 新登录端点 `/api/auth/login/new` 返回 access_token + refresh_token
- [ ] 刷新端点 `/api/auth/refresh` 正常工作
- [ ] 超级管理员在启动时自动创建/更新
- [ ] 所有测试通过

---

**P0 核心功能完成。继续执行 P1 管理功能计划。**
