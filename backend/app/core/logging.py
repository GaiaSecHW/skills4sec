"""
结构化日志系统 - 请求追踪和性能监控
"""
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Optional
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# 上下文变量：存储请求 ID
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """日志过滤器：添加请求 ID"""
    def filter(self, record):
        record.request_id = request_id_ctx.get() or "-"
        return True


class TimestampFilter(logging.Filter):
    """日志过滤器：添加时间戳"""
    def filter(self, record):
        record.timestamp = datetime.utcnow().isoformat() + "Z"
        return True


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    """
    配置结构化日志

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        json_format: 是否使用 JSON 格式（生产环境推荐）
    """
    log_format = (
        '{"timestamp": "%(timestamp)s", "level": "%(levelname)s", '
        '"request_id": "%(request_id)s", "name": "%(name)s", '
        '"message": %(message)s}\n'
        if json_format
        else "%(timestamp)s | %(levelname)-8s | %(request_id)-12s | %(name)s | %(message)s\n"
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format))
    handler.addFilter(RequestIdFilter())
    handler.addFilter(TimestampFilter())

    # 配置根日志
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    root_logger.handlers = [handler]

    # 降低第三方库日志级别
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("tortoise").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取带请求 ID 的日志记录器"""
    return logging.getLogger(name)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    def __init__(self, app, exclude_paths: Optional[set] = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or {"/health", "/metrics", "/"}
        self.logger = get_logger("http")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 跳过不需要记录的路径
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # 生成请求 ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:12]
        request_id_ctx.set(request_id)
        request.state.request_id = request_id

        # 记录请求开始
        start_time = time.perf_counter()
        self.logger.info(
            f'{{"method": "{request.method}", "path": "{request.url.path}", '
            f'"client": "{request.client.host if request.client else "-"}"}}'
        )

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # 记录请求完成
            self.logger.info(
                f'{{"status": {response.status_code}, "duration_ms": {duration_ms:.2f}}}'
            )

            # 添加请求 ID 到响应头
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.logger.error(
                f'{{"error": "{str(e)}", "duration_ms": {duration_ms:.2f}}}'
            )
            raise
