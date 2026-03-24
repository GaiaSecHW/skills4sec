# Harness Logging - 现有代码迁移实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有代码迁移到新日志系统，包括 gitea_sync_service、retry_service、scheduler、API 路由等

**Architecture:** 按模块逐步迁移，每模块独立测试

**Tech Stack:** FastAPI, structlog>=23.1.0,<24.0.0

---

## 概述

迁移策略：
1. 新代码直接使用 `HarnessLogger`
2. 旧代码按模块逐步迁移
3. 保持向后兼容，直到完全迁移

---

## Chunk 1: 准备 - 创建使用示例

### Task 1: 创建迁移示例文档

**Files:**
- Create: `backend/docs/logging_migration_guide.md`

- [ ] **Step 1: 编写迁移指南**

```markdown
# 日志迁移指南

## 旧代码（logging.py）

```python
from app.core import get_logger

logger = get_logger("gitea_sync")
logger.info(f'{{"event": "issue_fetch_failed", "issue_number": {issue_number}}}')
```

## 新代码（HarnessLogger）

```python
from app.core.harness_logging import HarnessLogger

logger = HarnessLogger("sync")
logger.info(
    "Issue 获取失败",
    event="issue_fetch_failed",
    business={"issue_number": issue_number},
)
```

## 主要变化

| 旧 | 新 |
|---|---|
| `get_logger(name)` | `HarnessLogger(module)` |
| JSON 字符串内嵌 | 结构化字段 |
| `event` 在 JSON 内 | `event` 作为顶级字段 |
| 无错误码 | 可选 `error_code` 字段 |
| 无敏感数据脱敏 | 自动脱敏 |

## 字段映射

| 场景 | 旧字段 | 新字段 |
|------|--------|--------|
| 业务 ID | JSON 内 `submission_id` | `business={"submission_id": "..."}` |
| 请求参数 | JSON 内 `params` | `params={...}` |
| 操作人 | JSON 内 `actor` | `actor={...}` |
| 错误信息 | JSON 内 `error` | `error={...}` |
```

- [ ] **Step 2: 提交**

```bash
git add backend/docs/logging_migration_guide.md
git commit -m "docs: add logging migration guide"
```

---

## Chunk 2: 迁移 gitea_sync_service

### Task 2: 迁移 gitea_sync_service.py

**Files:**
- Modify: `backend/app/services/gitea_sync_service.py`

- [ ] **Step 1: 读取现有代码**

Run: `cat backend/app/services/gitea_sync_service.py | head -100`

- [ ] **Step 2: 替换导入**

```python
# 替换原有
# from app.core import get_logger
# logger = get_logger("gitea_sync")

# 改为
from app.core.harness_logging import HarnessLogger

logger = HarnessLogger("sync")
```

- [ ] **Step 3: 替换日志调用**

找到类似这样的旧代码：
```python
logger.info(f'{{"event": "issue_fetch_success", "issue_number": {issue_number}}}')
```

替换为：
```python
logger.info(
    "Issue 获取成功",
    event="issue_fetch_success",
    business={"issue_number": issue_number},
)
```

- [ ] **Step 4: 替换错误日志**

找到类似这样的旧代码：
```python
logger.error(f'{{"event": "issue_fetch_failed", "issue_number": {issue_number}, "error": "{e}"}}')
```

替换为：
```python
logger.error(
    "Issue 获取失败",
    event="issue_fetch_failed",
    error=e,
    business={"issue_number": issue_number},
)
```

- [ ] **Step 5: 运行测试**

Run: `cd backend && py -m pytest tests/test_gitea_sync_service.py -v`
Expected: All tests passed（如果存在）或验证语法

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/gitea_sync_service.py
git commit -m "refactor: migrate gitea_sync_service to HarnessLogger"
```

---

## Chunk 3: 迁移 retry_service

### Task 3: 迁移 retry_service.py

**Files:**
- Modify: `backend/app/services/retry_service.py`

- [ ] **Step 1: 替换导入**

```python
# 替换为
from app.core.harness_logging import HarnessLogger

logger = HarnessLogger("retry")
```

- [ ] **Step 2: 替换日志调用**

旧代码：
```python
logger.info(f'{{"event": "retry_attempt", "attempt": {attempt}, "max_attempts": {max_attempts}}}')
```

新代码：
```python
logger.info(
    "重试尝试",
    event="retry_attempt",
    business={"attempt": attempt, "max_attempts": max_attempts},
)
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/services/retry_service.py
git commit -m "refactor: migrate retry_service to HarnessLogger"
```

---

## Chunk 4: 迁移 scheduler

### Task 4: 迁移 scheduler.py

**Files:**
- Modify: `backend/app/tasks/scheduler.py`

- [ ] **Step 1: 替换导入**

```python
from app.core.harness_logging import HarnessLogger

logger = HarnessLogger("scheduler")
```

- [ ] **Step 2: 替换日志调用**

- [ ] **Step 3: 提交**

```bash
git add backend/app/tasks/scheduler.py
git commit -m "refactor: migrate scheduler to HarnessLogger"
```

---

## Chunk 5: 迁移 submission_tasks

### Task 5: 迁移 submission_tasks.py

**Files:**
- Modify: `backend/app/tasks/submission_tasks.py`

- [ ] **Step 1: 替换导入**

```python
from app.core.harness_logging import HarnessLogger

logger = HarnessLogger("submission_tasks")
```

- [ ] **Step 2: 替换日志调用**

- [ ] **Step 3: 提交**

```bash
git add backend/app/tasks/submission_tasks.py
git commit -m "refactor: migrate submission_tasks to HarnessLogger"
```

---

## Chunk 6: 迁移 API 路由

### Task 6: 迁移 API 路由日志

**Files:**
- Modify: `backend/app/api/skills.py`
- Modify: `backend/app/api/submissions.py`
- Modify: `backend/app/api/admin/users.py`
- Modify: `backend/app/api/auth.py`

- [ ] **Step 1: 迁移 skills.py**

```python
from app.core.harness_logging import HarnessLogger

logger = HarnessLogger("skills")
```

替换路由内的日志调用。

- [ ] **Step 2: 迁移 submissions.py**

```python
logger = HarnessLogger("submissions")
```

- [ ] **Step 3: 迁移 admin/users.py**

```python
logger = HarnessLogger("admin_users")
```

- [ ] **Step 4: 迁移 auth.py**

```python
logger = HarnessLogger("auth")
```

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/skills.py
git add backend/app/api/submissions.py
git add backend/app/api/admin/users.py
git add backend/app/api/auth.py
git commit -m "refactor: migrate API routes to HarnessLogger"
```

---

## Chunk 7: 集成测试

### Task 7: 运行完整测试

**Files:**
- Modify: `backend/tests/test_logging_integration.py`

- [ ] **Step 1: 编写集成测试**

```python
# backend/tests/test_logging_integration.py
"""日志系统集成测试"""
import pytest
from app.core.harness_logging import (
    HarnessLogger,
    AuditLogger,
    ErrorCode,
    setup_harness_logging,
)
from app.core.exceptions import NotFoundError


class TestLoggingIntegration:
    """日志系统集成测试"""

    def test_harness_logger_with_error_code(self):
        """测试日志器带错误码"""
        logger = HarnessLogger("test")
        logger.error(
            "operation failed",
            event="operation_failed",
            error_code=ErrorCode.SUBM_500_01[0],
        )

    def test_audit_logger_basic(self):
        """测试审计日志"""
        audit = AuditLogger()
        audit.log(
            action="test_action",
            actor={"employee_id": "EMP001", "name": "测试"},
            target={"type": "test", "id": "123"},
            result="success",
        )

    def test_exception_with_error_code(self):
        """测试异常带错误码"""
        try:
            raise NotFoundError(
                message="用户不存在",
                error_code=ErrorCode.USER_404_01[0],
            )
        except NotFoundError as e:
            assert e.error_code == "USER-404-01"

    def test_full_logging_flow(self):
        """测试完整日志流程"""
        # 1. 创建日志器
        logger = HarnessLogger("test_flow")

        # 2. 记录正常日志
        logger.info(
            "operation success",
            event="operation_success",
            business={"id": "123"},
            params={"key": "value"},
        )

        # 3. 记录带 actor 的日志
        logger.info(
            "user action",
            event="user_action",
            actor={"employee_id": "EMP001", "name": "张三"},
            business={"id": "456"},
        )

        # 4. 记录错误日志
        try:
            raise ValueError("test error")
        except ValueError as e:
            logger.error(
                "operation error",
                event="operation_error",
                exception=e,
                error_code=ErrorCode.SYS_500_02[0],
            )
```

- [ ] **Step 2: 运行集成测试**

Run: `cd backend && py -m pytest tests/test_logging_integration.py -v`
Expected: All tests passed

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_logging_integration.py
git commit -m "test: add logging integration tests"
```

---

## Chunk 8: 清理旧代码

### Task 8: 清理旧的 logging.py（可选，稍后执行）

**Files:**
- Modify: `backend/app/core/logging.py`

**注意**: 此任务可选，建议在所有迁移完成后再执行。

- [ ] **Step 1: 确认无引用**

Run: `cd backend && grep -r "from app.core.logging import" --include="*.py" | grep -v test | grep -v "__pycache__"`
Expected: 仅剩 `harness_logging` 内部引用

- [ ] **Step 2: 标记为弃用**

```python
# backend/app/core/logging.py
"""
弃用：此模块已被 app.core.harness_logging 取代
请使用：
    from app.core.harness_logging import HarnessLogger
"""
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/logging.py
git commit -m "deprecate: mark old logging.py as deprecated"
```

---

## 依赖关系

此计划依赖所有其他计划（01-06）完成。

此计划完成后，Harness Logging 重构完成。
