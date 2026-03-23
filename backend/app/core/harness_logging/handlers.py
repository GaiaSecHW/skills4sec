"""日志文件处理器"""
import sys
from pathlib import Path
from typing import Optional
from loguru import logger
from app.core.harness_logging.config import LogConfig


def setup_file_handlers(config: LogConfig) -> None:
    """配置日志文件处理器"""
    # 移除默认 handler
    logger.remove()

    # 添加控制台 handler（调试用）
    logger.add(
        sys.stderr,
        level="DEBUG",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    )

    # 添加文件 handlers
    for name, handler_config in config.HANDLERS.items():
        logger.add(
            sink=str(config.LOG_DIR / handler_config["filename"]),
            level=handler_config["level"],
            rotation="50 MB",
            retention=f"{handler_config['retention_days']} days",
            compression="gz",
            serialize=True,  # JSON 格式
            enqueue=True,    # 异步写入
            backtrace=True,
            diagnose=True,
        )


def setup_logging(level: str = "INFO") -> None:
    """设置日志系统"""
    # 配置日志级别
    logger.level = level

    # 设置所有 handler
    setup_file_handlers(LogConfig)
