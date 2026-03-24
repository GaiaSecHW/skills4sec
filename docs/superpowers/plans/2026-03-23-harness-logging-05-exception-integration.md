# Harness Logging - AppException 集成实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 AppException 与新日志系统的集成，包括结构化错误日志、与 ErrorCode 关联

**Architecture:** 修改现有异常类 + 异常处理器中使用 HarnessLogger

**Tech Stack:** FastAPI, structlog>=23.1.0,<24.0.0

---

## 概述

此计划已完成于 **Plan 03: 错误码体系** 的 Chunk 3 和 Chunk 4。

本计划仅作为确认和补充测试。

---

## Chunk 1: 确认 AppException 修改

### Task 1: 验证 AppException 集成

**Files:**
- Modify: `backend/app/core/exceptions.py`

- [ ] **Step 1: 验证 error_code 字段存在**

Run: `cd backend && py -c "
from app.core.exceptions import AppException, NotFoundError, ValidationError

# 测试 AppException
e = AppException('test', error_code='TEST-500-01', suggestion='try again')
assert e.error_code == 'TEST-500-01'
assert e.suggestion == 'try again'

# 测试子类
ne = NotFoundError('not found', error_code='USER-404-01')
assert ne.error_code == 'USER-404-01'

print('OK')
"`
Expected: OK

- [ ] **Step 2: 验证异常处理器输出结构化日志**

Run: `cd backend && py -c "
from app.core.exceptions import ErrorResponse
print(ErrorResponse.model_fields.keys())
"`
Expected: dict_keys(['code', 'message', 'error_code', 'suggestion', 'detail', 'request_id'])

---

## Chunk 2: 集成测试

### Task 2: 编写 AppException 与日志集成测试

**Files:**
- Create: `backend/tests/test_exception_logging.py`

- [ ] **Step 1: 编写测试**

```python
# backend/tests/test_exception_logging.py
"""AppException 日志集成测试"""
import pytest
from app.core.exceptions import (
    AppException,
    NotFoundError,
    ValidationError,
    UnauthorizedError,
    ForbiddenError,
    ConflictError,
    DatabaseError,
)
from app.core.harness_logging.error_codes import ErrorCode


class TestAppExceptionErrorCode:
    """AppException error_code 字段测试"""

    def test_app_exception_default_error_code(self):
        """测试默认 error_code"""
        e = AppException("test error")
        assert e.error_code == "SYS-500-01"  # 默认值

    def test_app_exception_custom_error_code(self):
        """测试自定义 error_code"""
        e = AppException("test error", error_code="TEST-400-01")
        assert e.error_code == "TEST-400-01"

    def test_app_exception_with_suggestion(self):
        """测试 suggestion 字段"""
        e = AppException("test error", suggestion="please retry")
        assert e.suggestion == "please retry"

    def test_not_found_error_default(self):
        """测试 NotFoundError 默认 error_code"""
        e = NotFoundError("user not found")
        assert e.status_code == 404
        assert e.code == "NOT_FOUND"

    def test_not_found_error_custom(self):
        """测试 NotFoundError 自定义 error_code"""
        e = NotFoundError("user not found", error_code="USER-404-01")
        assert e.error_code == "USER-404-01"

    def test_validation_error(self):
        """测试 ValidationError"""
        e = ValidationError("invalid data", error_code="USER-400-01")
        assert e.status_code == 422
        assert e.error_code == "USER-400-01"

    def test_unauthorized_error(self):
        """测试 UnauthorizedError"""
        e = UnauthorizedError("token expired", error_code="AUTH-401-01")
        assert e.status_code == 401
        assert e.error_code == "AUTH-401-01"

    def test_forbidden_error(self):
        """测试 ForbiddenError"""
        e = ForbiddenError("no permission", error_code="AUTH-403-01")
        assert e.status_code == 403
        assert e.error_code == "AUTH-403-01"

    def test_conflict_error(self):
        """测试 ConflictError"""
        e = ConflictError("already exists", error_code="USER-409-01")
        assert e.status_code == 409
        assert e.error_code == "USER-409-01"

    def test_database_error(self):
        """测试 DatabaseError"""
        e = DatabaseError("db failed", error_code="SYS-500-01")
        assert e.status_code == 500
        assert e.error_code == "SYS-500-01"


class TestErrorCodeWithException:
    """ErrorCode 与 Exception 配合使用测试"""

    def test_use_error_code_tuple(self):
        """测试使用 ErrorCode 元组"""
        code, message, suggestion = ErrorCode.USER_404_01
        e = NotFoundError(
            message=message,
            error_code=code,
            detail={"user_id": "EMP001"},
        )
        assert e.message == "用户不存在"
        assert e.error_code == "USER-404-01"
        assert e.suggestion is None  # suggestion 需要单独传

    def test_use_error_code_get(self):
        """测试使用 ErrorCode.get()"""
        code, message, suggestion = ErrorCode.get("AUTH-401-01")
        e = UnauthorizedError(
            message=message,
            error_code=code,
            suggestion=suggestion,
        )
        assert e.error_code == "AUTH-401-01"
        assert e.suggestion == "请重新登录"

    def test_error_code_in_detail(self):
        """测试将 error_code 放入 detail"""
        e = NotFoundError(
            message="用户不存在",
            error_code="USER-404-01",
            detail={"error_code": "USER-404-01", "recovered": False},
        )
        assert e.detail["error_code"] == "USER-404-01"
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && py -m pytest tests/test_exception_logging.py -v`
Expected: All tests passed

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_exception_logging.py
git commit -m "test: add AppException logging integration tests"
```

---

## 依赖关系

此计划依赖：
- Plan 03: 错误码体系

此计划完成后，可解锁：
- Plan 07: 代码迁移
