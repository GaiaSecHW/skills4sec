# Harness Logging - AuditLogger 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现审计日志记录器 AuditLogger，支持双轨审计（文件 + 数据库）

**Architecture:** 审计日志写入 audit.log + 可选写入数据库模型

**Tech Stack:** structlog>=23.1.0,<24.0.0, loguru

---

## Chunk 1: AuditLogger 实现

### Task 1: 实现 AuditLogger

**Files:**
- Create: `backend/app/core/harness_logging/audit.py`

- [ ] **Step 1: 编写 AuditLogger 类**

```python
# backend/app/core/harness_logging/audit.py
"""审计日志记录器"""
from typing import Dict, Optional, Any
from datetime import datetime
from app.core.harness_logging.logger import HarnessLogger, trace_id_ctx, actor_ctx


# 需要写入数据库的审计动作
_DB_AUDIT_ACTIONS = {
    "user_login",
    "user_logout",
    "user_created",
    "user_updated",
    "user_deleted",
    "skill_approved",
    "skill_rejected",
    "submission_created",
    "submission_updated",
}


class AuditLogger:
    """
    审计日志记录器

    使用双轨策略：
    - 文件：logs/audit.log（90天保留）
    - 数据库：AuditLog 表（可选）

    使用场景：
    - 用户登录/登出 → 同时写入两者
    - 数据变更操作 → 同时写入两者
    - 内部系统操作 → 仅写入文件
    """

    def __init__(self, module: str = "audit"):
        self.file_logger = HarnessLogger(module)
        self._db_model = None  # 延迟导入

    def _get_db_model(self):
        """延迟获取数据库模型"""
        if self._db_model is None:
            try:
                from app.models.audit import AuditLog
                self._db_model = AuditLog
            except ImportError:
                pass
        return self._db_model

    def _should_persist_to_db(self, action: str) -> bool:
        """检查是否需要写入数据库"""
        return action in _DB_AUDIT_ACTIONS

    async def _persist_to_db(
        self,
        action: str,
        actor: Dict[str, Any],
        target: Dict[str, Any],
        result: str,
        details: Optional[Dict] = None,
    ) -> None:
        """写入数据库"""
        AuditLog = self._get_db_model()
        if AuditLog is None:
            return

        try:
            await AuditLog.create(
                action=action,
                actor_id=actor.get("employee_id"),
                actor_name=actor.get("name"),
                target_type=target.get("type"),
                target_id=target.get("id"),
                result=result,
                details=details,
                ip_address=actor.get("ip"),
            )
        except Exception as e:
            # 数据库写入失败不影响审计（已有文件日志）
            self.file_logger.warning(
                "audit_db_write_failed",
                event="audit_db_write_failed",
                error=str(e),
                action=action,
            )

    def log(
        self,
        action: str,
        actor: Dict[str, Any],
        target: Dict[str, Any],
        result: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        记录审计日志

        Args:
            action: 动作名称，如 "user_login", "skill_approved"
            actor: 操作人信息 {"employee_id": "EMP001", "name": "张三", "ip": "192.168.1.1"}
            target: 目标信息 {"type": "user", "id": "EMP001"}
            result: 结果 "success" | "failed" | "denied"
            details: 额外详情
        """
        # 补充 trace_id
        trace_id = trace_id_ctx.get()
        if trace_id:
            details = details or {}
            details["trace_id"] = trace_id

        # 1. 写入文件日志
        self.file_logger.info(
            f"Audit: {action}",
            event=f"audit_{action}",
            actor=actor,
            target=target,
            result=result,
            details=details,
        )

    async def log_async(
        self,
        action: str,
        actor: Dict[str, Any],
        target: Dict[str, Any],
        result: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        异步记录审计日志（包含数据库写入）

        Args:
            action: 动作名称
            actor: 操作人信息
            target: 目标信息
            result: 结果
            details: 额外详情
        """
        # 补充 trace_id
        trace_id = trace_id_ctx.get()
        if trace_id:
            details = details or {}
            details["trace_id"] = trace_id

        # 1. 写入文件日志
        self.file_logger.info(
            f"Audit: {action}",
            event=f"audit_{action}",
            actor=actor,
            target=target,
            result=result,
            details=details,
        )

        # 2. 可选：写入数据库
        if self._should_persist_to_db(action):
            await self._persist_to_db(action, actor, target, result, details)

    # ========== 常用审计动作快捷方法 ==========

    def user_login(
        self,
        employee_id: str,
        name: str,
        ip: str,
        method: str = "api_key",
        success: bool = True,
    ) -> None:
        """用户登录审计"""
        self.log(
            action="user_login",
            actor={"employee_id": employee_id, "name": name, "ip": ip},
            target={"type": "user", "id": employee_id},
            result="success" if success else "failed",
            details={"method": method},
        )

    def user_logout(
        self,
        employee_id: str,
        name: str,
        ip: str,
    ) -> None:
        """用户登出审计"""
        self.log(
            action="user_logout",
            actor={"employee_id": employee_id, "name": name, "ip": ip},
            target={"type": "user", "id": employee_id},
            result="success",
        )

    def skill_approved(
        self,
        admin_employee_id: str,
        admin_name: str,
        submission_id: str,
        skill_name: str,
        issue_number: int,
    ) -> None:
        """技能审批通过审计"""
        self.log(
            action="skill_approved",
            actor={"employee_id": admin_employee_id, "name": admin_name},
            target={"type": "submission", "id": submission_id},
            result="success",
            details={"skill_name": skill_name, "issue_number": issue_number},
        )

    def skill_rejected(
        self,
        admin_employee_id: str,
        admin_name: str,
        submission_id: str,
        reason: str,
    ) -> None:
        """技能审批拒绝审计"""
        self.log(
            action="skill_rejected",
            actor={"employee_id": admin_employee_id, "name": admin_name},
            target={"type": "submission", "id": submission_id},
            result="success",
            details={"reason": reason},
        )
```

- [ ] **Step 2: 验证语法**

Run: `cd backend && py -c "from app.core.harness_logging.audit import AuditLogger; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/harness_logging/audit.py
git commit -m "feat: add AuditLogger class"
```

---

## Chunk 2: AuditLogger 测试

### Task 2: 编写 AuditLogger 测试

**Files:**
- Create: `backend/tests/test_audit_logger.py`

- [ ] **Step 1: 编写测试**

```python
# backend/tests/test_audit_logger.py
"""AuditLogger 测试"""
import pytest
from app.core.harness_logging.audit import AuditLogger, _DB_AUDIT_ACTIONS


class TestAuditLogger:
    """AuditLogger 测试"""

    def test_audit_logger_creation(self):
        """测试 AuditLogger 创建"""
        audit = AuditLogger()
        assert audit.file_logger is not None

    def test_should_persist_to_db(self):
        """测试数据库持久化判断"""
        audit = AuditLogger()

        # 应该在数据库的动作
        assert audit._should_persist_to_db("user_login") is True
        assert audit._should_persist_to_db("skill_approved") is True
        assert audit._should_persist_to_db("submission_created") is True

        # 不应该在数据库的动作
        assert audit._should_persist_to_db("internal_action") is False
        assert audit._should_persist_to_db("cache_cleared") is False

    def test_log_no_exception(self):
        """测试 log 方法不抛异常"""
        audit = AuditLogger()
        # 不应抛异常
        audit.log(
            action="test_action",
            actor={"employee_id": "EMP001", "name": "测试"},
            target={"type": "test", "id": "123"},
            result="success",
        )

    def test_user_login_shortcut(self):
        """测试 user_login 快捷方法"""
        audit = AuditLogger()
        # 不应抛异常
        audit.user_login(
            employee_id="EMP001",
            name="张三",
            ip="192.168.1.100",
            method="api_key",
        )

    def test_skill_approved_shortcut(self):
        """测试 skill_approved 快捷方法"""
        audit = AuditLogger()
        # 不应抛异常
        audit.skill_approved(
            admin_employee_id="ADMIN01",
            admin_name="管理员",
            submission_id="SUB-001",
            skill_name="SQL注入检测",
            issue_number=42,
        )


class TestDbAuditActions:
    """数据库审计动作测试"""

    def test_db_audit_actions_defined(self):
        """测试数据库审计动作集合"""
        assert "user_login" in _DB_AUDIT_ACTIONS
        assert "user_logout" in _DB_AUDIT_ACTIONS
        assert "skill_approved" in _DB_AUDIT_ACTIONS
        assert "skill_rejected" in _DB_AUDIT_ACTIONS
        assert "submission_created" in _DB_AUDIT_ACTIONS

    def test_db_audit_actions_count(self):
        """测试数据库审计动作数量"""
        assert len(_DB_AUDIT_ACTIONS) >= 5
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && py -m pytest tests/test_audit_logger.py -v`
Expected: All tests passed

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_audit_logger.py
git commit -m "test: add AuditLogger tests"
```

---

## Chunk 3: 更新导出接口

### Task 3: 更新 __init__.py 导出 AuditLogger

**Files:**
- Modify: `backend/app/core/harness_logging/__init__.py`

- [ ] **Step 1: 更新导出**

```python
# backend/app/core/harness_logging/__init__.py - 添加导出
from app.core.harness_logging.audit import AuditLogger

__all__ = [
    "HarnessLogger",
    "HarnessLoggingMiddleware",
    "AuditLogger",
    "LogConfig",
    "setup_harness_logging",
    "trace_id_ctx",
    "span_id_ctx",
    "actor_ctx",
    "request_id_ctx",
    "mask_sensitive_data",
    "ErrorCode",
]
```

- [ ] **Step 2: 验证导出**

Run: `cd backend && py -c "from app.core.harness_logging import AuditLogger; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/harness_logging/__init__.py
git commit -m "feat: export AuditLogger class"
```

---

## 依赖关系

此计划依赖：
- Plan 01: 核心基础设施

此计划完成后，可解锁：
- Plan 07: 代码迁移
