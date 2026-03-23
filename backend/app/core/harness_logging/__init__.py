# backend/app/core/harness_logging/__init__.py
"""Harness Logging 模块 - 统一日志接口"""
from app.core.harness_logging.config import LogConfig
from app.core.harness_logging.handlers import setup_file_handlers
from app.core.harness_logging.logger import (
    HarnessLogger,
    trace_id_ctx,
    span_id_ctx,
    actor_ctx,
    setup_aggregator,
    stop_aggregator,
)
from app.core.harness_logging.middleware import HarnessLoggingMiddleware
from app.core.harness_logging.error_codes import ErrorCode
from app.core.harness_logging.processors import mask_sensitive_data
from app.core.logging import request_id_ctx  # 复用现有上下文

# 版本
__version__ = "1.0.0"


async def setup_harness_logging(
    level: str = "INFO",
    log_dir: str = "logs",
    service_name: str = "SecAgentHub",
    enable_aggregation: bool = True,
) -> None:
    """
    初始化 Harness 日志系统

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        log_dir: 日志目录
        service_name: 服务名称
        enable_aggregation: 是否启用日志聚合
    """
    from pathlib import Path

    # 配置
    LogConfig.SERVICE_NAME = service_name
    LogConfig.LOG_DIR = Path(log_dir)
    LogConfig.LOG_DIR.mkdir(exist_ok=True)
    LogConfig.LEVEL = level
    LogConfig.AGGREGATION_ENABLED = enable_aggregation

    # 设置文件 handlers
    setup_file_handlers(LogConfig)

    # 启动聚合器
    if enable_aggregation:
        await setup_aggregator(LogConfig)


__all__ = [
    "HarnessLogger",
    "HarnessLoggingMiddleware",
    "LogConfig",
    "setup_harness_logging",
    "setup_aggregator",
    "stop_aggregator",
    "trace_id_ctx",
    "span_id_ctx",
    "actor_ctx",
    "request_id_ctx",  # 复用现有
    "mask_sensitive_data",  # 新增
    "ErrorCode",  # 新增
]
