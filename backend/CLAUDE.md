# Backend - FastAPI + Tortoise-ORM 项目

## 项目启动

```bash
# 启动开发服务器
py main.py

# 或者使用 uvicorn
py -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## ⚠️ Windows 环境注意事项

**必须使用 `py` 命令，而非 `python` 或 `pip`**

在 Windows 环境下，直接使用 `python` 或 `pip` 可能会遇到以下错误：

```
Error: Exit code 49
Python was not found; run without arguments to install from the Microsoft Store,
or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.
```

❌ **错误用法**：
```bash
python -m app.main      # 会报错
pip install aiomysql    # 会报错
```

✅ **正确用法**：
```bash
py -m app.main          # 正确
py -m pip install aiomysql  # 正确
```

## 项目结构

```
app/
├── core/                    # 核心模块 - 最佳实践组件
│   ├── exceptions.py       # 全局异常处理
│   ├── logging.py          # 结构化日志 + 请求追踪
│   ├── database.py         # 事务管理 + 批量操作
│   ├── base_repository.py  # Repository 基类
│   └── dependencies.py     # FastAPI 依赖注入
├── repositories/            # 数据访问层 (Repository 模式)
│   ├── user_repository.py
│   └── skill_repository.py
├── api/                     # API 路由
├── models/                  # Tortoise-ORM 模型
├── schemas/                 # Pydantic Schemas
├── services/                # 业务逻辑
├── utils/                   # 工具函数
└── tasks/                   # 定时任务
```

---

## 编码规范（必须遵守）

### 1. 数据访问层 - 必须使用 Repository 模式

❌ **禁止**：在 API 层直接操作 ORM

```python
# 错误示例
@router.get("/users")
async def list_users():
    query = User.all()
    users = await query.offset(0).limit(20)
    return users

@router.post("/users")
async def create_user(data: UserCreate):
    if await User.exists(employee_id=data.employee_id):
        raise HTTPException(...)
    user = await User.create(...)
```

✅ **正确**：使用 Repository 封装数据访问

```python
from app.repositories import UserRepository
from app.core import get_repository

@router.get("/users")
async def list_users(
    repo: UserRepository = Depends(get_repository(UserRepository))
):
    return await repo.list_all(skip=0, limit=20)

@router.post("/users")
async def create_user(
    data: UserCreate,
    repo: UserRepository = Depends(get_repository(UserRepository))
):
    if await repo.exists(employee_id=data.employee_id):
        raise ConflictError(message="工号已存在")
    return await repo.create(**data.model_dump())
```

### 2. 异常处理 - 必须使用自定义异常

❌ **禁止**：使用 `HTTPException`

```python
# 错误示例
raise HTTPException(status_code=404, detail="用户不存在")
raise HTTPException(status_code=400, detail="工号已存在")
raise HTTPException(status_code=403, detail="权限不足")
raise HTTPException(status_code=401, detail="未授权")
raise HTTPException(status_code=422, detail="数据验证失败")
```

✅ **正确**：使用 `app.core` 中的自定义异常

```python
from app.core import (
    NotFoundError,      # 404
    ConflictError,      # 409
    ForbiddenError,     # 403
    UnauthorizedError,  # 401
    ValidationError,    # 422
    DatabaseError,      # 500
)

# 正确示例
raise NotFoundError(message="用户不存在", detail={"id": user_id})
raise ConflictError(message="工号已存在", detail={"employee_id": employee_id})
raise ForbiddenError(message="权限不足")
raise UnauthorizedError(message="登录已过期")
raise ValidationError(message="数据格式错误", detail=errors)
```

### 3. 分页参数 - 必须使用 PaginationParams

❌ **禁止**：手动定义分页参数

```python
# 错误示例
@router.get("/users")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    ...
```

✅ **正确**：使用 PaginationParams 依赖

```python
from app.core import PaginationParams, get_pagination

@router.get("/users")
async def list_users(
    pagination: PaginationParams = get_pagination(),
    repo: UserRepository = Depends(get_repository(UserRepository))
):
    # pagination.page      - 当前页码
    # pagination.page_size - 每页数量
    # pagination.skip      - 偏移量 (= (page-1) * page_size)
    # pagination.limit     - 限制数量 (= page_size)

    return await repo.paginate(
        page=pagination.page,
        page_size=pagination.page_size
    )
```

### 4. 日志 - 必须使用结构化日志

❌ **禁止**：使用 print 或普通 logging

```python
# 错误示例
print(f"[Init] 用户创建成功: {user_id}")
logger = logging.getLogger(__name__)
logger.info(f"User {user_id} created")
```

✅ **正确**：使用 `get_logger` + JSON 格式

```python
from app.core import get_logger

logger = get_logger("module_name")

# 使用 JSON 格式，便于日志分析
logger.info('{"event": "user_created", "user_id": 123}')
logger.error('{"event": "create_failed", "error": "database_error"}')
```

### 5. 事务管理 - 多表操作必须使用事务

❌ **禁止**：多表操作不使用事务

```python
# 错误示例 - 第二个 create 失败时，第一个已经写入
async def create_order():
    order = await Order.create(...)
    await OrderItem.create(...)  # 如果失败，order 已经创建
```

✅ **正确**：使用 `@atomic` 装饰器或 `transaction` 上下文

```python
from app.core import atomic, transaction

# 方式1：装饰器
@atomic
async def create_order():
    order = await Order.create(...)
    await OrderItem.create(...)
    # 任一失败自动回滚

# 方式2：上下文管理器
async def create_order():
    async with transaction():
        order = await Order.create(...)
        await OrderItem.create(...)
```

### 6. 权限校验 - 使用依赖注入

❌ **禁止**：在函数内手动校验权限

```python
# 错误示例
@router.delete("/users/{user_id}")
async def delete_user(user_id: int, current_user: User = Depends(get_current_user)):
    if current_user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="权限不足")
    ...
```

✅ **正确**：使用权限依赖

```python
from app.core import get_admin_user, get_super_admin

# 需要管理员权限
@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(get_admin_user)  # 自动校验
):
    ...

# 需要超级管理员权限
@router.post("/users/batch")
async def batch_create_users(
    admin: User = Depends(get_super_admin)  # 自动校验
):
    ...
```

---

## Repository 开发指南

### 创建新 Repository

```python
# app/repositories/order_repository.py
from typing import Optional, List
from app.core.base_repository import BaseRepository
from app.models.order import Order

class OrderRepository(BaseRepository[Order]):
    """订单数据访问层"""

    model_class = Order

    async def find_by_user(self, user_id: int, skip: int = 0, limit: int = 100) -> List[Order]:
        """获取用户订单"""
        return await self.model_class.filter(
            user_id=user_id
        ).offset(skip).limit(limit).order_by("-created_at")

    async def count_pending(self) -> int:
        """统计待处理订单"""
        return await self.model_class.filter(status="pending").count()
```

### BaseRepository 提供的方法

```python
# 读取
await repo.get_by_id(id)              # 获取单条，不存在抛异常
await repo.get_by_id_or_none(id)      # 获取单条，不存在返回 None
await repo.get_one(**filters)         # 按条件获取
await repo.list_all(skip, limit)      # 列表查询
await repo.count(**filters)           # 计数
await repo.exists(**filters)          # 是否存在
await repo.paginate(page, page_size)  # 分页查询

# 写入
await repo.create(**data)             # 创建
await repo.update(instance, **data)   # 更新
await repo.update_by_id(id, **data)   # 按 ID 更新
await repo.delete(instance)           # 删除
await repo.delete_by_id(id)           # 按 ID 删除
```

---

## 核心组件使用

### 异常处理

```python
from app.core import NotFoundError, ValidationError, ForbiddenError, ConflictError

# 抛出业务异常（自动转换为统一 JSON 响应）
raise NotFoundError(message="用户不存在", detail={"id": user_id})
raise ValidationError(message="数据格式错误", detail=errors)
raise ForbiddenError(message="权限不足")
raise ConflictError(message="资源已存在")
```

### 依赖注入

```python
from app.core import (
    get_pagination,       # 分页参数
    get_current_user_dep, # 当前用户
    get_admin_user,       # 管理员
    get_super_admin,      # 超级管理员
    get_repository,       # Repository 工厂
)
```

### 数据库工具

```python
from app.core import (
    atomic,           # 事务装饰器
    transaction,      # 事务上下文
    bulk_create,      # 批量创建
    bulk_update,      # 批量更新
    check_database_health,  # 健康检查
)
```

---

## 数据库迁移

```bash
# 初始化迁移
aerich init-db

# 生成迁移文件
aerich migrate --name "description"

# 执行迁移
aerich upgrade

# 回滚
aerich downgrade
```

## 测试

```bash
# 运行测试
pytest

# 带覆盖率
pytest --cov=app

# 运行单个测试文件
pytest tests/test_auth_api.py -v
```

## 环境变量

复制 `.env.example` 为 `.env` 并配置：

```
DATABASE_URL=sqlite://db.sqlite3
SECRET_KEY=your-secret-key
DEBUG=True
GITEA_API_URL=http://localhost:3000/api/v1
GITEA_TOKEN=your-gitea-token
GITEA_REPO=owner/repo
```
