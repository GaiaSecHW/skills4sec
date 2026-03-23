# backend/tests/test_harness_logging_core.py
"""Harness Logging 核心测试"""
import pytest
from pathlib import Path
from app.core.harness_logging.config import LogConfig
from app.core.harness_logging.logger import HarnessLogger


def test_log_config_defaults():
    """测试配置默认值"""
    assert LogConfig.SERVICE_NAME == "SecAgentHub"
    # LEVEL 可能被 main.py 中的 setup_harness_logging 修改 (DEBUG when settings.DEBUG=True)
    assert LogConfig.LEVEL in ("DEBUG", "INFO")
    assert LogConfig.AGGREGATION_ENABLED is True
    assert "app" in LogConfig.HANDLERS
    assert "error" in LogConfig.HANDLERS


def test_harness_logger_creation():
    """测试日志器创建"""
    logger = HarnessLogger("test")
    assert logger.module == "test"


def test_harness_logger_info():
    """测试 info 日志"""
    logger = HarnessLogger("test")
    # 不应抛出异常
    logger.info("test message", event="test_event")


def test_harness_logger_error():
    """测试 error 日志"""
    logger = HarnessLogger("test")
    try:
        raise ValueError("test error")
    except ValueError as e:
        logger.error("error occurred", exception=e, event="test_error")


def test_harness_logger_with_business():
    """测试带 business 字段"""
    logger = HarnessLogger("test")
    logger.info(
        "operation success",
        event="operation_success",
        business={"id": "123", "name": "test"},
    )
