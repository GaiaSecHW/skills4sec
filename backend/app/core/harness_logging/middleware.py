"""HarnessLoggingMiddleware - 请求日志中间件"""
import time
import uuid
from typing import Optional, Set
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from app.core.logging import request_id_ctx  # 复用现有上下文
from app.core.harness_logging.logger import trace_id_ctx, span_id_ctx, actor_ctx
from app.core.harness_logging.logger import HarnessLogger


class HarnessLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件 - 替换原 RequestLoggingMiddleware"""

    def __init__(
        self,
        app,
        exclude_paths: Optional[Set[str]] = None,
        logger_name: str = "http",
    ):
        super().__init__(app)
        self.exclude_paths = exclude_paths or {"/health", "/metrics", "/", "/favicon.ico"}
        self.logger = HarnessLogger(logger_name)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 跳过不需要记录的路径
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # 生成请求 ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:12]
        request_id_ctx.set(request_id)  # 复用现有上下文
        request.state.request_id = request_id

        # 设置新日志系统的上下文
        trace_id_ctx.set(request_id)
        span_id_ctx.set(str(uuid.uuid4())[:8])

        # 提取 actor 信息
        actor = self._extract_actor(request)
        if actor:
            actor_ctx.set(actor)

        # 记录请求开始
        start_time = time.perf_counter()
        self.logger.info(
            "请求开始",
            event="request_started",
            params={
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else "-",
            },
        )

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # 记录请求完成
            self.logger.info(
                "请求完成",
                event="request_completed",
                duration_ms=round(duration_ms, 2),
                business={"status_code": response.status_code},
            )

            # 添加请求 ID 到响应头
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.logger.error(
                "请求异常",
                event="request_error",
                exception=e,
                duration_ms=round(duration_ms, 2),
            )
            raise

    def _extract_actor(self, request: Request) -> dict:
        """提取操作人信息"""
        actor = {}

        # 从请求状态获取用户信息（如果已登录）
        if hasattr(request.state, "user"):
            user = request.state.user
            if hasattr(user, "employee_id"):
                actor["employee_id"] = user.employee_id
            if hasattr(user, "name"):
                actor["name"] = user.name

        return actor
