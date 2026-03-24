# Harness Logging - 错误码体系实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现分层错误码体系 `{模块}-{HTTP状态码}-{序号}`，包括错误码定义、错误码获取、与 AppException 集成

**Architecture:** 错误码类定义 + 与现有 AppException 体系集成

**Tech Stack:** Python, FastAPI

---

## Chunk 1: 错误码定义

### Task 1: 实现 error_codes.py

**Files:**
- Create: `backend/app/core/harness_logging/error_codes.py`

- [ ] **Step 1: 编写错误码类**

```python
# backend/app/core/harness_logging/error_codes.py
"""错误码定义

格式: {模块}-{HTTP状态码}-{序号}
示例: AUTH-401-01, SUBM-500-01
"""
from typing import Tuple, Optional


class ErrorCode:
    """错误码定义"""

    # ========== AUTH 认证模块 ==========
    AUTH_401_01 = ("AUTH-401-01", "Token 已过期", "请重新登录")
    AUTH_401_02 = ("AUTH-401-02", "Token 无效", "Token 格式错误或被篡改")
    AUTH_401_03 = ("AUTH-401-03", "API Key 无效", "请检查 API Key 是否正确")
    AUTH_401_04 = ("AUTH-401-04", "登录已过期", "请重新登录")
    AUTH_403_01 = ("AUTH-403-01", "权限不足", "需要管理员权限")
    AUTH_403_02 = ("AUTH-403-02", "访问被拒绝", "您没有权限访问此资源")
    AUTH_429_01 = ("AUTH-429-01", "登录失败次数过多", "账户已锁定 30 分钟")

    # ========== USER 用户模块 ==========
    USER_404_01 = ("USER-404-01", "用户不存在", "请检查工号是否正确")
    USER_404_02 = ("USER-404-02", "用户已禁用", "请联系管理员")
    USER_409_01 = ("USER-409-01", "工号已存在", "该工号已被注册")
    USER_409_02 = ("USER-409-02", "邮箱已注册", "该邮箱已被使用")
    USER_400_01 = ("USER-400-01", "API Key 格式错误", "长度需至少 6 位")
    USER_400_02 = ("USER-400-02", "工号格式错误", "工号格式不正确")

    # ========== SUBM 技能提交模块 ==========
    SUBM_400_01 = ("SUBM-400-01", "提交参数不完整", "缺少必填字段")
    SUBM_400_02 = ("SUBM-400-02", "提交参数无效", "请检查参数格式")
    SUBM_404_01 = ("SUBM-404-01", "提交记录不存在", "submission_id 无效")
    SUBM_409_01 = ("SUBM-409-01", "重复提交", "该技能已提交过")
    SUBM_409_02 = ("SUBM-409-02", "提交状态不允许", "当前状态不允许此操作")
    SUBM_500_01 = ("SUBM-500-01", "Issue 创建失败", "Gitea API 返回错误")
    SUBM_500_02 = ("SUBM-500-02", "提交处理失败", "服务器内部错误")

    # ========== SKILL 技能模块 ==========
    SKILL_404_01 = ("SKILL-404-01", "技能不存在", "技能 ID 无效")
    SKILL_409_01 = ("SKILL-409-01", "技能已存在", "同名技能已存在")
    SKILL_400_01 = ("SKILL-400-01", "技能参数错误", "请检查技能配置")

    # ========== SYNC 同步模块 ==========
    SYNC_503_01 = ("SYNC-503-01", "Gitea API 超时", "服务无响应，请稍后重试")
    SYNC_502_01 = ("SYNC-502-01", "Gitea API 错误", "上游服务返回异常")
    SYNC_401_01 = ("SYNC-401-01", "Gitea Token 无效", "请检查配置")
    SYNC_404_01 = ("SYNC-404-01", "Gitea 仓库不存在", "请检查仓库地址")

    # ========== ADMIN 管理模块 ==========
    ADMIN_403_01 = ("ADMIN-403-01", "需要管理员权限", "此操作需要管理员权限")
    ADMIN_403_02 = ("ADMIN-403-02", "需要超级管理员权限", "此操作需要超级管理员权限")

    # ========== SYS 系统模块 ==========
    SYS_500_01 = ("SYS-500-01", "数据库连接失败", "请检查数据库状态")
    SYS_500_02 = ("SYS-500-02", "内部服务错误", "请联系管理员")
    SYS_500_03 = ("SYS-500-03", "缓存服务错误", "请稍后重试")
    SYS_503_01 = ("SYS-503-01", "服务暂不可用", "服务正在维护中")

    @classmethod
    def get(cls, code: str) -> Tuple[str, str, str]:
        """
        获取错误码详情

        Args:
            code: 错误码字符串，如 "AUTH-401-01"

        Returns:
            (code, message, suggestion) 元组
        """
        # 使用 getattr 查找类属性
        attr_name = code.replace("-", "_").replace(" ", "_")
        result = getattr(cls, attr_name, None)

        if result:
            return result

        # 未找到，返回默认值
        return (code, "未知错误", "请联系管理员")

    @classmethod
    def get_message(cls, code: str) -> str:
        """获取错误消息"""
        return cls.get(code)[1]

    @classmethod
    def get_suggestion(cls, code: str) -> str:
        """获取解决建议"""
        return cls.get(code)[2]
```

- [ ] **Step 2: 验证语法**

Run: `cd backend && py -c "from app.core.harness_logging.error_codes import ErrorCode; print(ErrorCode.AUTH_401_01); print(ErrorCode.get('AUTH-401-01'))"`
Expected: ('AUTH-401-01', 'Token 已过期', '请重新登录')

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/harness_logging/error_codes.py
git commit -m "feat: add ErrorCode class with predefined error codes"
```

---

## Chunk 2: 错误码测试

### Task 2: 编写错误码测试

**Files:**
- Create: `backend/tests/test_error_codes.py`

- [ ] **Step 1: 编写测试**

```python
# backend/tests/test_error_codes.py
"""错误码测试"""
import pytest
from app.core.harness_logging.error_codes import ErrorCode


class TestErrorCode:
    """错误码测试"""

    def test_error_code_format(self):
        """测试错误码格式"""
        code, message, suggestion = ErrorCode.AUTH_401_01
        assert code == "AUTH-401-01"
        assert message == "Token 已过期"
        assert suggestion == "请重新登录"

    def test_get_existing_code(self):
        """测试获取已定义的错误码"""
        result = ErrorCode.get("AUTH-401-01")
        assert result == ("AUTH-401-01", "Token 已过期", "请重新登录")

    def test_get_nonexistent_code(self):
        """测试获取未定义的错误码"""
        result = ErrorCode.get("UNKNOWN-999-99")
        assert result == ("UNKNOWN-999-99", "未知错误", "请联系管理员")

    def test_get_message(self):
        """测试获取错误消息"""
        assert ErrorCode.get_message("USER-404-01") == "用户不存在"

    def test_get_suggestion(self):
        """测试获取解决建议"""
        assert ErrorCode.get_suggestion("AUTH-401-01") == "请重新登录"

    def test_all_auth_codes(self):
        """测试所有认证错误码"""
        assert ErrorCode.AUTH_401_01 == ("AUTH-401-01", "Token 已过期", "请重新登录")
        assert ErrorCode.AUTH_401_02 == ("AUTH-401-02", "Token 无效", "Token 格式错误或被篡改")
        assert ErrorCode.AUTH_401_03 == ("AUTH-401-03", "API Key 无效", "请检查 API Key 是否正确")
        assert ErrorCode.AUTH_403_01 == ("AUTH-403-01", "权限不足", "需要管理员权限")
        assert ErrorCode.AUTH_429_01 == ("AUTH-429-01", "登录失败次数过多", "账户已锁定 30 分钟")

    def test_all_user_codes(self):
        """测试所有用户错误码"""
        assert ErrorCode.USER_404_01 == ("USER-404-01", "用户不存在", "请检查工号是否正确")
        assert ErrorCode.USER_409_01 == ("USER-409-01", "工号已存在", "该工号已被注册")

    def test_all_subm_codes(self):
        """测试所有提交错误码"""
        assert ErrorCode.SUBM_400_01 == ("SUBM-400-01", "提交参数不完整", "缺少必填字段")
        assert ErrorCode.SUBM_404_01 == ("SUBM-404-01", "提交记录不存在", "submission_id 无效")
        assert ErrorCode.SUBM_409_01 == ("SUBM-409-01", "重复提交", "该技能已提交过")
        assert ErrorCode.SUBM_500_01 == ("SUBM-500-01", "Issue 创建失败", "Gitea API 返回错误")

    def test_all_sync_codes(self):
        """测试所有同步错误码"""
        assert ErrorCode.SYNC_503_01 == ("SYNC-503-01", "Gitea API 超时", "服务无响应，请稍后重试")
        assert ErrorCode.SYNC_401_01 == ("SYNC-401-01", "Gitea Token 无效", "请检查配置")

    def test_all_sys_codes(self):
        """测试所有系统错误码"""
        assert ErrorCode.SYS_500_01 == ("SYS-500-01", "数据库连接失败", "请检查数据库状态")
        assert ErrorCode.SYS_500_02 == ("SYS-500-02", "内部服务错误", "请联系管理员")
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && py -m pytest tests/test_error_codes.py -v`
Expected: All tests passed

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_error_codes.py
git commit -m "test: add ErrorCode tests"
```

---

## Chunk 3: 与 AppException 集成

### Task 3: 修改 AppException 添加 error_code 字段

**Files:**
- Modify: `backend/app/core/exceptions.py`

- [ ] **Step 1: 修改 AppException 类**

```python
# backend/app/core/exceptions.py - 修改 AppException
class AppException(Exception):
    """应用基础异常"""
    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: str = None,  # 新增：分层业务码
        detail: Optional[Any] = None,
        suggestion: str = None,  # 新增：解决建议
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.error_code = error_code or f"SYS-{status_code}-01"  # 默认错误码
        self.detail = detail
        self.suggestion = suggestion
        super().__init__(self.message)
```

- [ ] **Step 2: 修改 NotFoundError 等子类**

```python
# backend/app/core/exceptions.py - 修改 NotFoundError
class NotFoundError(AppException):
    """资源未找到"""
    def __init__(self, message: str = "资源未找到", error_code: str = None, detail: Optional[Any] = None):
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code=error_code,
            detail=detail,
        )
```

- [ ] **Step 3: 修改 ValidationError**

```python
class ValidationError(AppException):
    """验证错误"""
    def __init__(self, message: str = "数据验证失败", error_code: str = None, detail: Optional[Any] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=error_code,
            detail=detail,
        )
```

- [ ] **Step 4: 修改 UnauthorizedError**

```python
class UnauthorizedError(AppException):
    """未授权"""
    def __init__(self, message: str = "未授权访问", error_code: str = None, detail: Optional[Any] = None):
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code=error_code,
            detail=detail,
        )
```

- [ ] **Step 5: 修改 ForbiddenError**

```python
class ForbiddenError(AppException):
    """禁止访问"""
    def __init__(self, message: str = "权限不足", error_code: str = None, detail: Optional[Any] = None):
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
            error_code=error_code,
            detail=detail,
        )
```

- [ ] **Step 6: 修改 ConflictError**

```python
class ConflictError(AppException):
    """资源冲突"""
    def __init__(self, message: str = "资源已存在", error_code: str = None, detail: Optional[Any] = None):
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            error_code=error_code,
            detail=detail,
        )
```

- [ ] **Step 7: 修改 DatabaseError**

```python
class DatabaseError(AppException):
    """数据库错误"""
    def __init__(self, message: str = "数据库操作失败", error_code: str = None, detail: Optional[Any] = None):
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code=error_code,
            detail=detail,
        )
```

- [ ] **Step 8: 验证语法**

Run: `cd backend && py -c "from app.core.exceptions import AppException, NotFoundError; e = NotFoundError('用户不存在', error_code='USER-404-01'); print(e.error_code)"`
Expected: USER-404-01

- [ ] **Step 9: 提交**

```bash
git add backend/app/core/exceptions.py
git commit -m "feat: add error_code field to AppException"
```

---

## Chunk 4: 更新异常处理器集成日志

### Task 4: 更新异常处理器输出结构化日志

**Files:**
- Modify: `backend/app/core/exceptions.py`

- [ ] **Step 1: 添加 HarnessLogger 到异常处理器**

```python
# backend/app/core/exceptions.py - 添加导入和 logger
from app.core.harness_logging.logger import HarnessLogger

# 创建日志器
logger = HarnessLogger("exception")

# 修改 app_exception_handler
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """处理自定义异常"""
    request_id = getattr(request.state, "request_id", None)

    # 记录结构化错误日志
    logger.error(
        exc.message,
        event="exception_raised",
        error_code=exc.error_code,
        status_code=exc.status_code,
        detail=exc.detail,
        suggestion=exc.suggestion,
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=exc.code,
            message=exc.message,
            error_code=exc.error_code,
            detail=exc.detail,
            suggestion=exc.suggestion,
            request_id=request_id,
        ).model_dump(exclude_none=True),
    )
```

- [ ] **Step 2: 修改 ErrorResponse 添加 error_code 和 suggestion**

```python
# backend/app/core/exceptions.py - 修改 ErrorResponse
class ErrorResponse(BaseModel):
    """统一错误响应格式"""
    code: str
    message: str
    error_code: Optional[str] = None
    suggestion: Optional[str] = None
    detail: Optional[Any] = None
    request_id: Optional[str] = None
```

- [ ] **Step 3: 验证**

Run: `cd backend && py -c "from app.core.exceptions import ErrorResponse; print(ErrorResponse.model_fields.keys())"`
Expected: dict_keys(['code', 'message', 'error_code', 'suggestion', 'detail', 'request_id'])

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/exceptions.py
git commit -m "feat: integrate structured logging in exception handler"
```

---

## Chunk 5: 更新导出接口

### Task 5: 更新 __init__.py 导出 ErrorCode

**Files:**
- Modify: `backend/app/core/harness_logging/__init__.py`

- [ ] **Step 1: 更新导出**

```python
# backend/app/core/harness_logging/__init__.py - 添加导出
from app.core.harness_logging.error_codes import ErrorCode

__all__ = [
    "HarnessLogger",
    "HarnessLoggingMiddleware",
    "LogConfig",
    "setup_harness_logging",
    "trace_id_ctx",
    "span_id_ctx",
    "actor_ctx",
    "request_id_ctx",
    "mask_sensitive_data",
    "ErrorCode",  # 新增
]
```

- [ ] **Step 2: 验证导出**

Run: `cd backend && py -c "from app.core.harness_logging import ErrorCode; print(ErrorCode.AUTH_401_01)"`
Expected: ('AUTH-401-01', 'Token 已过期', '请重新登录')

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/harness_logging/__init__.py
git commit -m "feat: export ErrorCode class"
```

---

## 依赖关系

此计划**独立**，可与 Plan 01/02 并行执行。

此计划完成后，可解锁：
- Plan 05: AppException 集成（如果未完成，此计划已包含）
- Plan 07: 代码迁移（使用 ErrorCode）
