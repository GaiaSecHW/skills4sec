# 测试规范指南

基于 Harness Engineering 最佳实践，为 Backend (FastAPI + Tortoise-ORM) 项目制定的测试规范。

---

## 测试架构概览

### 测试金字塔

```
        /\
       /  \      E2E 测试 (端到端)
      /----\     - 少量，验证关键业务流程
     /      \
    /--------\   集成测试 (API + 数据库)
   /          \  - 适量，验证模块间协作
  /------------\
 /              \ 单元测试 (纯逻辑)
/________________\ - 大量，快速验证核心逻辑
```

### 当前测试分层

| 层级 | 目录/文件 | 职责 |
|------|----------|------|
| **单元测试** | `test_models.py`, `test_schemas.py` | 测试纯逻辑、数据模型 |
| **Repository 测试** | `test_*_repository.py` | 测试数据访问层 |
| **API 测试** | `test_*_api.py` | 测试 HTTP 端点 |
| **服务测试** | `test_*_service.py` | 测试业务逻辑层 |

---

## 核心原则

### 1. 测试隔离 (Test Isolation)

每个测试必须独立运行，不依赖其他测试的状态。

```python
# ❌ 错误：依赖其他测试创建的数据
class TestUser:
    test_id = None  # 类变量共享状态

    async def test_create(self, db):
        user = await User.create(...)
        self.test_id = user.id  # 其他测试可能依赖此值

    async def test_read(self, db):
        user = await User.get(id=self.test_id)  # 危险！

# ✅ 正确：每个测试独立准备数据
class TestUser:
    @pytest.mark.asyncio
    async def test_create(self, db):
        user = await User.create(employee_id="TEST001", ...)
        assert user.id is not None

    @pytest.mark.asyncio
    async def test_read(self, db, test_user):  # 使用 fixture
        user = await User.get(id=test_user.id)
        assert user.employee_id == "TEST001"
```

### 2. 单一职责 (Single Responsibility)

每个测试只验证一个行为。

```python
# ❌ 错误：一个测试验证多个行为
async def test_user_operations(self, db):
    user = await User.create(...)  # 创建
    user.name = "Updated"          # 更新
    await user.save()
    await user.delete()            # 删除

# ✅ 正确：拆分为独立测试
class TestUserCreate:
    async def test_create_success(self, db):
        user = await User.create(...)
        assert user.id is not None

class TestUserUpdate:
    async def test_update_name(self, db, test_user):
        test_user.name = "Updated"
        await test_user.save()
        assert test_user.name == "Updated"

class TestUserDelete:
    async def test_delete_success(self, db, test_user):
        await test_user.delete()
        assert await User.exists(id=test_user.id) is False
```

### 3. 边界值测试 (Boundary Testing)

必须测试边界条件和异常情况。

```python
class TestPagination:
    """分页边界值测试示例"""

    @pytest.mark.asyncio
    async def test_first_page(self, db):
        """第一页"""
        result = await repo.paginate(page=1, page_size=10)
        assert result["page"] == 1

    @pytest.mark.asyncio
    async def test_empty_page(self, db):
        """超出范围的页码 - 边界值"""
        result = await repo.paginate(page=9999, page_size=10)
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_page_size_min(self, db):
        """最小页码 - 边界值"""
        result = await repo.paginate(page=1, page_size=1)
        assert len(result["items"]) <= 1

    @pytest.mark.asyncio
    async def test_page_size_max(self, db):
        """最大页码 - 边界值"""
        result = await repo.paginate(page=1, page_size=100)
        assert len(result["items"]) <= 100

    @pytest.mark.asyncio
    async def test_id_zero(self, db):
        """ID 为 0 - 边界值"""
        result = await repo.get_by_id_or_none(0)
        assert result is None

    @pytest.mark.asyncio
    async def test_id_negative(self, db):
        """ID 为负数 - 边界值"""
        result = await repo.get_by_id_or_none(-1)
        assert result is None
```

### 4. 快速反馈 (Fast Feedback)

测试应该快速执行，支持频繁运行。

```python
# ❌ 错误：不必要的延迟
async def test_login(self, client):
    await asyncio.sleep(1)  # 不要人为延迟
    response = await client.post(...)

# ✅ 正确：直接测试
async def test_login(self, client):
    response = await client.post(...)
    assert response.status_code == 200
```

---

## 测试命名规范

### 文件命名

```
test_<模块名>.py          # 单元测试
test_<模块名>_api.py      # API 测试
test_<模块名>_repository.py  # Repository 测试
test_<模块名>_service.py  # Service 测试
```

### 类命名

```python
class Test<功能模块>:
    """测试类的 docstring 描述测试目标"""

class TestLoginByEmployeeId:    # ✅ 清晰描述功能
class Test_UserLogin:           # ❌ 不要用下划线开头
class test_login:               # ❌ 类名用 PascalCase
```

### 方法命名

```python
# 模式：test_<方法名>_<场景>_<预期结果>

# ✅ 正确命名
async def test_create_success(self, db):                    # 正常情况
async def test_create_duplicate_raises_conflict(self, db):  # 异常情况
async def test_login_invalid_password_returns_401(self):    # 包含状态码
async def test_get_by_id_not_exists_returns_none(self):     # 边界值

# ❌ 错误命名
async def test_create(self):           # 不明确
async def test_create_1(self):         # 无意义数字
async def testCreate(self):            # 驼峰命名
```

---

## Fixtures 使用规范

### 标准 Fixtures (conftest.py)

```python
# conftest.py 提供的 fixtures:

db                # 数据库连接 (function scope)
client            # HTTP 客户端 (function scope)
test_user         # 普通用户
admin_user        # 管理员用户
super_admin_user  # 超级管理员
auth_headers      # 用户认证头
admin_auth_headers # 管理员认证头
super_auth_headers # 超管认证头
test_category     # 测试分类
test_skill        # 测试技能
```

### 自定义 Fixtures

```python
@pytest_asyncio.fixture
async def test_submission(db, test_user, test_skill):
    """创建测试提交记录"""
    from app.models.submission import Submission

    submission = await Submission.create(
        user=test_user,
        skill=test_skill,
        status="pending",
    )
    return submission


@pytest_asyncio.fixture
async def multiple_submissions(db, test_user):
    """创建多个提交记录用于分页测试"""
    from app.models.submission import Submission

    submissions = []
    for i in range(15):
        sub = await Submission.create(
            user=test_user,
            status="pending",
        )
        submissions.append(sub)
    return submissions
```

### Fixture Scope 选择

| Scope | 用途 | 示例 |
|-------|------|------|
| `function` | 默认，每个测试独立 | `db`, `client`, `test_user` |
| `class` | 类内共享 | 共享的配置数据 |
| `module` | 模块内共享 | 昂贵的资源初始化 |
| `session` | 整个测试会话共享 | `event_loop` |

---

## 测试分类模板

### 1. API 测试模板

```python
"""
Tests for <模块名> API endpoints
"""
import pytest
from httpx import AsyncClient

from app.models.user import User


class Test<EndpointName>:
    """Test <端点描述>"""

    @pytest.mark.asyncio
    async def test_<action>_success(self, client: AsyncClient, test_user: User):
        """Test successful <action>"""
        response = await client.post(
            "/api/path",
            json={"key": "value"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "expected_field" in data

    @pytest.mark.asyncio
    async def test_<action>_unauthorized(self, client: AsyncClient):
        """Test <action> without auth"""
        response = await client.post("/api/path", json={})

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_<action>_invalid_data(self, client: AsyncClient, auth_headers: dict):
        """Test <action> with invalid data"""
        response = await client.post(
            "/api/path",
            json={"invalid": "data"},
            headers=auth_headers
        )

        assert response.status_code == 422  # Validation error


class Test<AnotherEndpoint>:
    """Test another endpoint"""
    ...
```

### 2. Repository 测试模板

```python
"""
Tests for <名称> Repository - <描述>
"""
import pytest

from app.repositories.<name>_repository import <Name>Repository
from app.models.<model> import <Model>
from app.core.exceptions import NotFoundError


class Test<Name>RepositoryCreate:
    """Test create operations"""

    @pytest.mark.asyncio
    async def test_create_success(self, db):
        """Test successful creation"""
        repo = <Name>Repository()
        instance = await repo.create(field1="value1", field2="value2")

        assert instance.id is not None
        assert instance.field1 == "value1"

    @pytest.mark.asyncio
    async def test_create_duplicate_raises_error(self, db, test_instance):
        """Test duplicate creation raises error"""
        repo = <Name>Repository()

        with pytest.raises(ConflictError):
            await repo.create(unique_field=test_instance.unique_field)


class Test<Name>RepositoryRead:
    """Test read operations"""

    @pytest.mark.asyncio
    async def test_get_by_id_exists(self, db, test_instance):
        """Test getting existing record"""
        repo = <Name>Repository()
        result = await repo.get_by_id(test_instance.id)

        assert result.id == test_instance.id

    @pytest.mark.asyncio
    async def test_get_by_id_not_exists(self, db):
        """Test getting non-existent record - 边界值"""
        repo = <Name>Repository()

        with pytest.raises(NotFoundError):
            await repo.get_by_id(999999)

    @pytest.mark.asyncio
    async def test_get_by_id_or_none_not_exists(self, db):
        """Test get_by_id_or_none with non-existent ID"""
        repo = <Name>Repository()
        result = await repo.get_by_id_or_none(999999)

        assert result is None


class Test<Name>RepositoryUpdate:
    """Test update operations"""

    @pytest.mark.asyncio
    async def test_update_success(self, db, test_instance):
        """Test successful update"""
        repo = <Name>Repository()
        updated = await repo.update(test_instance, field1="new_value")

        assert updated.field1 == "new_value"


class Test<Name>RepositoryDelete:
    """Test delete operations"""

    @pytest.mark.asyncio
    async def test_delete_success(self, db, test_instance):
        """Test successful deletion"""
        repo = <Name>Repository()
        await repo.delete(test_instance)

        result = await repo.get_by_id_or_none(test_instance.id)
        assert result is None
```

### 3. Service 测试模板

```python
"""
Tests for <名称> Service
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.<name>_service import <Name>Service


class Test<Name>Service:
    """Test <Name>Service"""

    @pytest.fixture
    def service(self, db):
        """Create service instance"""
        return <Name>Service()

    @pytest.mark.asyncio
    async def test_<method>_success(self, service, test_user):
        """Test successful <method>"""
        result = await service.<method>(test_user.id)

        assert result is not None

    @pytest.mark.asyncio
    async def test_<method>_with_external_api(self, service):
        """Test <method> with mocked external API"""
        with patch.object(service, '_call_external') as mock_call:
            mock_call.return_value = {"status": "success"}

            result = await service.<method>()

            mock_call.assert_called_once()
            assert result["status"] == "success"
```

---

## Mock 和 Stub 使用

### 何时使用 Mock

```python
# ✅ 适合 Mock 的场景：
# 1. 外部 API 调用
# 2. 第三方服务
# 3. 耗时操作
# 4. 不确定的结果（随机数、时间）

# ❌ 不适合 Mock 的场景：
# 1. 数据库操作（使用测试数据库）
# 2. 业务逻辑
# 3. 简单的数据转换
```

### Mock 示例

```python
from unittest.mock import AsyncMock, patch, MagicMock

# Mock 异步函数
@patch("app.services.gitea_service.GiteaSyncService.create_file")
async def test_sync_to_gitea(self, mock_create, db, test_skill):
    """Test syncing to Gitea with mocked API"""
    mock_create.return_value = {"content": "file content"}

    service = GiteaSyncService()
    result = await service.sync_skill(test_skill)

    mock_create.assert_called_once()
    assert result["status"] == "success"


# Mock 依赖
async def test_with_mocked_repo(self, db):
    """Test with mocked repository"""
    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock(return_value=MockUser(id=1))

    # 注入 mock
    result = await mock_repo.get_by_id(1)
    assert result.id == 1
```

---

## 测试覆盖率

### 运行覆盖率测试

```bash
# 运行并生成覆盖率报告
pytest --cov=app --cov-report=term-missing

# 生成 HTML 报告
pytest --cov=app --cov-report=html

# 只测试特定模块
pytest --cov=app/repositories --cov-report=term-missing
```

### 覆盖率目标

| 模块 | 目标覆盖率 | 说明 |
|------|-----------|------|
| `app/core/` | 90%+ | 核心组件，必须高覆盖 |
| `app/repositories/` | 85%+ | 数据访问层 |
| `app/services/` | 80%+ | 业务逻辑层 |
| `app/api/` | 75%+ | API 端点 |
| `app/models/` | 60%+ | 模型验证 |

### 覆盖率排除

```python
# pragma: no cover - 排除单行
if DEBUG:  # pragma: no cover
    print("debug info")

# pragma: no cover - 排除整个函数
def deprecated_function():  # pragma: no cover
    pass
```

---

## 测试数据管理

### 测试数据命名规范

```python
# 使用明确的前缀标识测试数据
TEST_PREFIX = "TEST_"
employee_id="TEST001"      # ✅ 清晰标识
employee_id="test_user"    # ✅ 可接受
employee_id="abc"          # ❌ 不明确
employee_id="real_user"    # ❌ 可能混淆
```

### 测试数据清理

```python
# conftest.py 已配置 function scope，每个测试后自动清理
# 如需手动清理：

@pytest_asyncio.fixture
async def clean_db(db):
    """清理测试数据"""
    yield
    # 测试后清理
    await User.filter(employee_id__startswith="TEST_").delete()
```

---

## 常用命令

```bash
# 运行所有测试
pytest

# 运行特定文件
pytest tests/test_auth_api.py

# 运行特定测试类
pytest tests/test_auth_api.py::TestLoginByEmployeeId

# 运行特定测试方法
pytest tests/test_auth_api.py::TestLoginByEmployeeId::test_login_success

# 详细输出
pytest -v

# 显示 print 输出
pytest -s

# 并行运行（需要 pytest-xdist）
pytest -n auto

# 失败时停止
pytest -x

# 只运行上次失败的测试
pytest --lf

# 先运行上次失败的，再运行其他的
pytest --ff

# 带覆盖率
pytest --cov=app --cov-report=term-missing
```

---

## 最佳实践检查清单

### 编写测试前

- [ ] 理解被测试代码的功能
- [ ] 识别正常路径和异常路径
- [ ] 确定边界条件
- [ ] 检查是否有可复用的 fixtures

### 编写测试时

- [ ] 测试类使用清晰的 docstring
- [ ] 测试方法命名描述行为和预期结果
- [ ] 每个测试只验证一个行为
- [ ] 使用 `assert` 语句而非 `print`
- [ ] 测试数据使用有意义的值

### 编写测试后

- [ ] 测试可以独立运行
- [ ] 测试可以重复运行
- [ ] 测试快速执行
- [ ] 覆盖正常、异常、边界情况
- [ ] 没有硬编码的敏感信息

### 代码审查时

- [ ] 新代码有对应的测试
- [ ] 测试覆盖了关键业务逻辑
- [ ] 测试命名清晰易懂
- [ ] 测试不过度依赖 Mock

---

## 参考资源

- [pytest 官方文档](https://docs.pytest.org/)
- [pytest-asyncio 文档](https://pytest-asyncio.readthedocs.io/)
- [FastAPI 测试指南](https://fastapi.tiangolo.com/tutorial/testing/)
- [Tortoise-ORM 测试](https://tortoise.github.io/examples/fastapi.html)
