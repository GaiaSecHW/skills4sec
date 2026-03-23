"""日志系统集成测试"""
import pytest
from app.core.harness_logging import (
    HarnessLogger,
    AuditLogger,
    ErrorCode,
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
        logger = HarnessLogger("test_flow")

        logger.info(
            "operation success",
            event="operation_success",
            business={"id": "123"},
            params={"key": "value"},
        )

        logger.info(
            "user action",
            event="user_action",
            actor={"employee_id": "EMP001", "name": "张三"},
            business={"id": "456"},
        )

        try:
            raise ValueError("test error")
        except ValueError as e:
            logger.error(
                "operation error",
                event="operation_error",
                exception=e,
                error_code=ErrorCode.SYS_500_02[0],
            )
