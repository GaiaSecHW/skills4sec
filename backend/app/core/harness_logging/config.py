"""日志配置"""
from pathlib import Path
from typing import Dict, Any
from app.core.logging import request_id_ctx


class AggregatorConfig:
    """
    聚合器配置

    注意：
    - 单 Worker 模式：启用内存聚合
    - 多 Worker 模式：禁用聚合（每个 Worker 有独立缓存）
    - 生产环境多 Worker 时设置 AGGREGATION_ENABLED = False
    """
    ENABLED = True
    WINDOW_SECONDS = 60
    MAX_CACHE = 1000


class LogConfig:
    """日志配置"""

    # 服务名称
    SERVICE_NAME = "SecAgentHub"

    # 日志目录
    LOG_DIR = Path("logs")
    LOG_DIR.mkdir(exist_ok=True)

    # 日志级别
    LEVEL = "INFO"

    # 是否启用聚合（多 Worker 时设为 False）
    AGGREGATION_ENABLED = True

    # Handler 配置
    HANDLERS: Dict[str, Dict[str, Any]] = {
        "app": {
            "filename": "app.log",
            "level": "DEBUG",
            "retention_days": 30,
        },
        "error": {
            "filename": "error.log",
            "level": "ERROR",
            "retention_days": 30,
        },
        "access": {
            "filename": "access.log",
            "level": "INFO",
            "retention_days": 30,
        },
        "audit": {
            "filename": "audit.log",
            "level": "INFO",
            "retention_days": 90,
        },
    }

    # 聚合配置
    AGGREGATION = {
        "window_seconds": 60,
        "max_cache": 1000,
    }
