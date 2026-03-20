# 用户管理模块 - P1 管理功能实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现管理后台 API（用户 CRUD、登录日志查询）和前端管理页面

**Architecture:** 新建 admin.py API 路由，实现用户管理、日志查询；修改前端 app.js 添加管理后台路由和页面

**Tech Stack:** FastAPI, Tortoise ORM, SPA (原生 JS)

**前置条件:** P0 核心功能已完成

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/api/admin.py` | 新建 | 管理后台 API |
| `backend/app/main.py` | 修改 | 注册 admin 路由 |
| `docs/assets/app.js` | 修改 | 添加管理后台前端 |

---

## Task 1: 创建管理后台 API - 用户列表

**Files:**
- Create: `backend/app/api/admin.py`

- [ ] **Step 1: 创建 admin.py 基础结构和用户列表端点**

```python
# backend/app/api/admin.py
from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional
from datetime import datetime

from app.models.user import User
from app.models.login_log import LoginLog
from app.models.admin_log import AdminLog
from app.schemas.user import UserOutNew, UserCreateByAdmin, UserUpdateByAdmin
from app.schemas.log import LoginLogOut, AdminLogOut
from app.utils.security import (
    get_current_admin_user,
    get_current_super_admin,
    hash_api_key,
    validate_api_key_complexity,
)
from app.utils.pagination import paginate
from app.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])


# ============ 用户管理 ============

@router.get("/users", response_model=dict)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    employee_id: Optional[str] = None,
    name: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    admin: User = Depends(get_current_admin_user)
):
    """
    获取用户列表 (管理员)

    支持按工号、姓名、角色、状态筛选
    """
    query = User.all()

    if employee_id:
        query = query.filter(employee_id__icontains=employee_id)
    if name:
        query = query.filter(name__icontains=name)
    if role:
        query = query.filter(role=role)
    if status:
        query = query.filter(status=status)

    total = await query.count()
    users = await query.offset(skip).limit(limit).order_by("-created_at")

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [UserOutNew.model_validate(u) for u in users]
    }
```

- [ ] **Step 2: 验证语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.api.admin import router; print('Admin router OK')"
```
Expected: `Admin router OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin.py
git commit -m "feat(admin): add user list endpoint with filters

- Support filter by employee_id, name, role, status
- Require admin role to access
- Return paginated results

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 添加用户创建/查询/更新/删除

**Files:**
- Modify: `backend/app/api/admin.py`

- [ ] **Step 1: 添加用户 CRUD 端点**

在 `list_users` 函数后添加：

```python
@router.post("/users", response_model=UserOutNew, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreateByAdmin,
    admin: User = Depends(get_current_admin_user)
):
    """新增用户 (管理员)"""
    # 验证 API 密钥复杂度
    valid, msg = validate_api_key_complexity(user_data.api_key)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    # 检查工号是否已存在
    if await User.exists(employee_id=user_data.employee_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="工号已存在"
        )

    user = await User.create(
        employee_id=user_data.employee_id,
        name=user_data.name,
        api_key_hash=hash_api_key(user_data.api_key),
        role=user_data.role,
        department=user_data.department,
        team=user_data.team,
        group_name=user_data.group_name,
        status="active",
    )

    # 记录操作日志
    await AdminLog.create(
        admin_id=admin.id,
        admin_employee_id=admin.employee_id,
        action="create_user",
        target_user_id=user.id,
        target_employee_id=user.employee_id,
        details={"name": user.name, "role": user.role},
    )

    return user


@router.get("/users/{user_id}", response_model=UserOutNew)
async def get_user(
    user_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """获取用户详情 (管理员)"""
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


@router.put("/users/{user_id}", response_model=UserOutNew)
async def update_user(
    user_id: int,
    update_data: UserUpdateByAdmin,
    admin: User = Depends(get_current_admin_user)
):
    """编辑用户 (管理员)"""
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    # 更新字段
    update_dict = update_data.model_dump(exclude_unset=True)

    # 如果更新 API 密钥，验证并哈希
    if "api_key" in update_dict and update_dict["api_key"]:
        valid, msg = validate_api_key_complexity(update_dict["api_key"])
        if not valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
        update_dict["api_key_hash"] = hash_api_key(update_dict["api_key"])
        del update_dict["api_key"]
    elif "api_key" in update_dict:
        del update_dict["api_key"]  # 空值不修改

    for key, value in update_dict.items():
        setattr(user, key, value)

    await user.save()

    # 记录操作日志
    await AdminLog.create(
        admin_id=admin.id,
        admin_employee_id=admin.employee_id,
        action="update_user",
        target_user_id=user.id,
        target_employee_id=user.employee_id,
        details=update_dict,
    )

    return user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """删除用户 (管理员)"""
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if user.role == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除超级管理员"
        )

    # 记录操作日志
    await AdminLog.create(
        admin_id=admin.id,
        admin_employee_id=admin.employee_id,
        action="delete_user",
        target_user_id=user.id,
        target_employee_id=user.employee_id,
        details={"name": user.name},
    )

    await user.delete()
    return {"success": True, "message": "用户已删除"}
```

- [ ] **Step 2: 验证语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.api.admin import create_user, get_user, update_user, delete_user; print('CRUD OK')"
```
Expected: `CRUD OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin.py
git commit -m "feat(admin): add user CRUD endpoints

- POST /users: create user with API key validation
- GET /users/{id}: get user detail
- PUT /users/{id}: update user (optional API key)
- DELETE /users/{id}: delete user (prevent super_admin deletion)
- Log all admin operations to AdminLog

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 添加重置密钥和切换状态端点

**Files:**
- Modify: `backend/app/api/admin.py`

- [ ] **Step 1: 添加重置密钥和切换状态端点**

在 `delete_user` 函数后添加：

```python
@router.post("/users/{user_id}/reset-key")
async def reset_user_api_key(
    user_id: int,
    new_key: str = Query(..., min_length=32, description="新的 API 密钥"),
    admin: User = Depends(get_current_admin_user)
):
    """重置用户 API 密钥 (管理员)"""
    valid, msg = validate_api_key_complexity(new_key)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    user.api_key_hash = hash_api_key(new_key)
    await user.save()

    await AdminLog.create(
        admin_id=admin.id,
        admin_employee_id=admin.employee_id,
        action="reset_key",
        target_user_id=user.id,
        target_employee_id=user.employee_id,
    )

    return {"success": True, "message": "API 密钥已重置"}


@router.post("/users/{user_id}/toggle-status", response_model=UserOutNew)
async def toggle_user_status(
    user_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """切换用户启用/禁用状态 (管理员)"""
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if user.role == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能禁用超级管理员"
        )

    user.status = "disabled" if user.status == "active" else "active"
    await user.save()

    await AdminLog.create(
        admin_id=admin.id,
        admin_employee_id=admin.employee_id,
        action="toggle_status",
        target_user_id=user.id,
        target_employee_id=user.employee_id,
        details={"new_status": user.status},
    )

    return user
```

- [ ] **Step 2: 验证语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.api.admin import reset_user_api_key, toggle_user_status; print('Status ops OK')"
```
Expected: `Status ops OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin.py
git commit -m "feat(admin): add reset-key and toggle-status endpoints

- POST /users/{id}/reset-key: reset user API key
- POST /users/{id}/toggle-status: enable/disable user
- Prevent operations on super_admin
- Log operations to AdminLog

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 添加登录日志查询

**Files:**
- Modify: `backend/app/api/admin.py`

- [ ] **Step 1: 添加登录日志查询端点**

```python
# ============ 日志查询 ============

@router.get("/login-logs", response_model=dict)
async def list_login_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    admin: User = Depends(get_current_admin_user)
):
    """获取登录日志列表 (管理员)"""
    query = LoginLog.all()

    if employee_id:
        query = query.filter(employee_id__icontains=employee_id)
    if status:
        query = query.filter(status=status)
    if start_date:
        query = query.filter(login_time__gte=start_date)
    if end_date:
        query = query.filter(login_time__lte=end_date)

    total = await query.count()
    logs = await query.offset(skip).limit(limit).order_by("-login_time")

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [LoginLogOut.model_validate(log) for log in logs]
    }
```

- [ ] **Step 2: 验证语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.api.admin import list_login_logs; print('Login logs OK')"
```
Expected: `Login logs OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin.py
git commit -m "feat(admin): add login logs query endpoint

- Support filter by employee_id, status, date range
- Return paginated results ordered by login_time desc

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: 添加操作日志查询（仅超级管理员）

**Files:**
- Modify: `backend/app/api/admin.py`

- [ ] **Step 1: 添加操作日志查询端点**

```python
@router.get("/admin-logs", response_model=dict)
async def list_admin_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    admin_id: Optional[int] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    super_admin: User = Depends(get_current_super_admin)
):
    """获取管理员操作日志列表 (仅超级管理员)"""
    query = AdminLog.all()

    if admin_id:
        query = query.filter(admin_id=admin_id)
    if action:
        query = query.filter(action=action)
    if start_date:
        query = query.filter(created_at__gte=start_date)
    if end_date:
        query = query.filter(created_at__lte=end_date)

    total = await query.count()
    logs = await query.offset(skip).limit(limit).order_by("-created_at")

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [AdminLogOut.model_validate(log) for log in logs]
    }
```

- [ ] **Step 2: 验证语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.api.admin import list_admin_logs; print('Admin logs OK')"
```
Expected: `Admin logs OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin.py
git commit -m "feat(admin): add admin logs query endpoint (super_admin only)

- Support filter by admin_id, action, date range
- Require super_admin role

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 注册 Admin 路由

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 添加 admin 路由导入和注册**

在导入部分添加：

```python
from app.api.admin import router as admin_router
```

在路由注册部分添加：

```python
app.include_router(admin_router, prefix="/api")
```

- [ ] **Step 2: 验证应用启动**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.main import app; print('App with admin OK')"
```
Expected: `App with admin OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(main): register admin router

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: 测试后端 API

**Files:**
- None

- [ ] **Step 1: 启动后端服务**

```bash
cd D:/work/skillhub/skills4sec/backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

- [ ] **Step 2: 登录获取 Token**

```bash
curl -X POST http://localhost:8001/api/auth/login/new \
  -H "Content-Type: application/json" \
  -d '{"employee_id":"w00000001","api_key":"your-secure-api-key-at-least-32-characters-long!"}'
```

保存返回的 `access_token`。

- [ ] **Step 3: 测试用户列表 API**

```bash
curl http://localhost:8001/api/admin/users \
  -H "Authorization: Bearer <your-access-token>"
```

Expected: JSON with `total`, `items` array.

- [ ] **Step 4: 测试创建用户**

```bash
curl -X POST http://localhost:8001/api/admin/users \
  -H "Authorization: Bearer <your-access-token>" \
  -H "Content-Type: application/json" \
  -d '{"employee_id":"w00000002","name":"张三","api_key":"test-api-key-with-at-least-32-characters","role":"user"}'
```

Expected: User JSON with `id`, `employee_id`, `name`, `role`.

---

## 验收标准

- [ ] `/api/admin/users` GET 返回用户列表
- [ ] `/api/admin/users` POST 创建新用户
- [ ] `/api/admin/users/{id}` GET/PUT/DELETE 正常工作
- [ ] `/api/admin/users/{id}/reset-key` 重置密钥
- [ ] `/api/admin/users/{id}/toggle-status` 切换状态
- [ ] `/api/admin/login-logs` 查询登录日志
- [ ] `/api/admin/admin-logs` 查询操作日志（仅超管）
- [ ] 所有操作记录到 AdminLog

---

**P1 管理功能完成。继续执行 P2 增强功能计划（批量导入导出、登录限流）。**
