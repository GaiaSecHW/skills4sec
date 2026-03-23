# backend/app/core/harness_logging/logger.py
"""HarnessLogger - 结构化日志记录器"""
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar
import loguru

from app.core.harness_logging.processors import mask_sensitive_data

# 上下文变量
trace_id_ctx: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
span_id_ctx: ContextVar[Optional[str]] = ContextVar("span_id", default=None)
actor_ctx: ContextVar[Optional[Dict]] = ContextVar("actor", default=None)

# 日志器实例
_loggers: Dict[str, loguru.Logger] = {}


def _get_logger(name: str) -> loguru.Logger:
    """获取或创建日志器"""
    if name not in _loggers:
        _loggers[name] = loguru.logger.bind(name=name)
    return _loggers[name]


class HarnessLogger:
    """结构化日志记录器"""

    def __init__(self, module: str):
        self.module = module
        self._logger = _get_logger(module)

    def _build_record(self, message: str, level: str, **kwargs) -> Dict[str, Any]:
        """构建日志记录"""
        now = datetime.utcnow()

        record = {
            "timestamp": now.isoformat() + "Z",
            "service": "SecAgentHub",
            "level": level,
            "module": self.module,
            "message": message,
            "event": kwargs.pop("event", f"{self.module}_{level.lower()}"),
            "trace_id": trace_id_ctx.get(),
            "span_id": span_id_ctx.get() or str(uuid.uuid4())[:8],
        }

        # 添加 actor
        actor = kwargs.pop("actor", None) or actor_ctx.get() or {}
        if actor:
            record["actor"] = actor

        # 添加 business
        business = kwargs.pop("business", None)
        if business:
            record["business"] = business

        # 添加 params
        params = kwargs.pop("params", None)
        if params:
            record["params"] = params

        # 添加 error
        error = kwargs.pop("error", None)
        if error:
            record["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
            if hasattr(error, "__traceback__"):
                import traceback
                record["error"]["stack_trace"] = "".join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                )

        # 添加 root_cause
        root_cause = kwargs.pop("root_cause", None)
        if root_cause:
            if "error" not in record:
                record["error"] = {}
            record["error"]["root_cause"] = root_cause

        # 添加 duration_ms
        duration_ms = kwargs.pop("duration_ms", None)
        if duration_ms:
            record["duration_ms"] = duration_ms

        # 添加额外字段
        record.update(kwargs)

        return record

    def _log(self, level: str, message: str, **kwargs) -> None:
        """内部日志方法"""
        try:
            record = self._build_record(message, level, **kwargs)
            # 添加脱敏处理
            record = mask_sensitive_data(record)
            self._logger.log(level, record)
        except Exception as e:
            # 容错：日志系统自身出错，降级到标准输出
            sys.stderr.write(f"[LOG_ERROR] {e}\n")

    def debug(self, message: str, **kwargs) -> None:
        self._log("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        self._log("ERROR", message, **kwargs)

    def exception(self, message: str, **kwargs) -> None:
        """记录异常信息"""
        kwargs.setdefault("error", kwargs.get("exception", None))
        self._log("ERROR", message, **kwargs)
