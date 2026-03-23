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
        audit.log(
            action="test_action",
            actor={"employee_id": "EMP001", "name": "测试"},
            target={"type": "test", "id": "123"},
            result="success",
        )

    def test_user_login_shortcut(self):
        """测试 user_login 快捷方法"""
        audit = AuditLogger()
        audit.user_login(
            employee_id="EMP001",
            name="张三",
            ip="192.168.1.100",
            method="api_key",
        )

    def test_skill_approved_shortcut(self):
        """测试 skill_approved 快捷方法"""
        audit = AuditLogger()
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
