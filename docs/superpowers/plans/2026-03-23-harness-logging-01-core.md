# Harness Logging - 核心基础设施实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 `app/core/harness_logging/` 模块核心基础设施，包括配置、logger封装、文件处理器、中间件

**Architecture:** 使用 structlog 23.x + loguru 实现结构化 JSON 日志，支持多文件输出（app.log/error.log/access.log/audit.log），复用现有 `request_id_ctx`

**Tech Stack:** structlog>=23.1.0,<24.0.0, loguru>=0.7.0, Python 3.10

---

## Chunk 1: 项目准备与依赖安装

### Task 1: 安装依赖

**Files:**
- Modify: `backend/requirements.txt` 或 `pyproject.toml`

- [ ] **Step 1: 添加依赖到项目**

```toml
# pyproject.toml 或 requirements.txt
structlog>=23.1.0,<24.0.0
loguru>=0.7.0
```

Run: `cd backend && py -m pip install structlog loguru`
Expected: Successfully installed structlog-23.x.x and loguru-0.7.x

- [ ] **Step 2: 验证依赖可用**

Run: `py -c "import structlog; import loguru; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add requirements.txt pyproject.toml
git commit -m "feat: add structlog and loguru dependencies"
```

---

## Chunk 2: 目录结构与配置

### Task 2: 创建 harness_logging 目录结构

**Files:**
- Create: `backend/app/core/harness_logging/__init__.py`
- Create: `backend/app/core/harness_logging/config.py`
- Create: `backend/app/core/harness_logging/logger.py`
- Create: `backend/app/core/harness_logging/handlers.py`
- Create: `backend/app/core/harness_logging/middleware.py`

- [ ] **Step 1: 创建目录和空 `__init__.py`**

```bash
mkdir -p backend/app/core/harness_logging
touch backend/app/core/harness_logging/__init__.py
```

- [ ] **Step 2: 提交初始结构**

```bash
git add backend/app/core/harness_logging/
git commit -m "feat: create harness_logging directory structure"
```

---

### Task 3: 实现 config.py

**Files:**
- Create: `backend/app/core/harness_logging/config.py`

- [ ] **Step 1: 编写配置类**

```python
# backend/app/core/harness_logging/config.py
"""日志配置"""
from pathlib import Path
from typing import Dict, Any
from app.core.logging import request_id_ctx


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
```

- [ ] **Step 2: 验证语法**

Run: `cd backend && py -c "from app.core.harness_logging.config import LogConfig; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/harness_logging/config.py
git commit -m "feat: add LogConfig class"
```

---

### Task 4: 实现 handlers.py

**Files:**
- Create: `backend/app/core/harness_logging/handlers.py`

- [ ] **Step 1: 编写文件处理器**

```python
# backend/app/core/harness_logging/handlers.py
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
```

- [ ] **Step 2: 验证语法**

Run: `cd backend && py -c "from app.core.harness_logging.handlers import setup_logging; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/harness_logging/handlers.py
git commit -m "feat: add file handlers for log rotation"
```

---

### Task 5: 实现 logger.py

**Files:**
- Create: `backend/app/core/harness_logging/logger.py`

- [ ] **Step 1: 编写 HarnessLogger 类**

```python
# backend/app/core/harness_logging/logger.py
"""HarnessLogger - 结构化日志记录器"""
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar
import loguru

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
```

- [ ] **Step 2: 验证语法**

Run: `cd backend && py -c "from app.core.harness_logging.logger import HarnessLogger; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/harness_logging/logger.py
git commit -m "feat: add HarnessLogger class"
```

---

### Task 6: 实现 middleware.py

**Files:**
- Create: `backend/app/core/harness_logging/middleware.py`

- [ ] **Step 1: 编写中间件**

```python
# backend/app/core/harness_logging/middleware.py
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
```

- [ ] **Step 2: 验证语法**

Run: `cd backend && py -c "from app.core.harness_logging.middleware import HarnessLoggingMiddleware; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/harness_logging/middleware.py
git commit -m "feat: add HarnessLoggingMiddleware"
```

---

## Chunk 3: 初始化与导出接口

### Task 7: 实现 setup_harness_logging 与导出接口

**Files:**
- Modify: `backend/app/core/harness_logging/__init__.py`

- [ ] **Step 1: 编写 `__init__.py` 导出接口**

```python
# backend/app/core/harness_logging/__init__.py
"""Harness Logging 模块 - 统一日志接口"""
from app.core.harness_logging.config import LogConfig
from app.core.harness_logging.handlers import setup_file_handlers
from app.core.harness_logging.logger import HarnessLogger, trace_id_ctx, span_id_ctx, actor_ctx
from app.core.harness_logging.middleware import HarnessLoggingMiddleware
from app.core.logging import request_id_ctx  # 复用现有上下文

# 版本
__version__ = "1.0.0"


def setup_harness_logging(
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


__all__ = [
    "HarnessLogger",
    "HarnessLoggingMiddleware",
    "LogConfig",
    "setup_harness_logging",
    "trace_id_ctx",
    "span_id_ctx",
    "actor_ctx",
    "request_id_ctx",  # 复用现有
]
```

- [ ] **Step 2: 验证导入**

Run: `cd backend && py -c "from app.core.harness_logging import setup_harness_logging, HarnessLogger; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/harness_logging/__init__.py
git commit -m "feat: export setup_harness_logging and HarnessLogger"
```

---

### Task 8: 更新 main.py 使用新日志系统

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 更新 main.py 导入**

```python
# app/main.py - 修改导入
# 替换原有
# from app.core.logging import setup_logging, RequestLoggingMiddleware
# 改为
from app.core.harness_logging import setup_harness_logging, HarnessLoggingMiddleware
```

- [ ] **Step 2: 替换初始化调用**

```python
# app/main.py - 替换初始化
# 替换原有
# setup_logging(level="DEBUG" if settings.DEBUG else "INFO", json_format=not settings.DEBUG)
# 改为
setup_harness_logging(
    level="DEBUG" if settings.DEBUG else "INFO",
    log_dir="logs",
    service_name="SecAgentHub",
    enable_aggregation=True,
)
```

- [ ] **Step 3: 替换中间件**

```python
# app/main.py - 替换中间件
# 替换原有
# app.add_middleware(RequestLoggingMiddleware, exclude_paths={"/health", "/metrics", "/", "/favicon.ico"})
# 改为
app.add_middleware(
    HarnessLoggingMiddleware,
    exclude_paths={"/health", "/metrics", "/", "/favicon.ico"},
)
```

- [ ] **Step 4: 验证启动**

Run: `cd backend && py -c "from app.main import app; print('OK')"`
Expected: OK (无报错)

- [ ] **Step 5: 提交**

```bash
git add backend/app/main.py
git commit -m "feat: integrate harness_logging in main.py"
```

---

## Chunk 4: 基础测试

### Task 9: 编写核心基础设施测试

**Files:**
- Create: `backend/tests/test_harness_logging_core.py`

- [ ] **Step 1: 编写测试**

```python
# backend/tests/test_harness_logging_core.py
"""Harness Logging 核心测试"""
import pytest
from pathlib import Path
from app.core.harness_logging.config import LogConfig
from app.core.harness_logging.logger import HarnessLogger


def test_log_config_defaults():
    """测试配置默认值"""
    assert LogConfig.SERVICE_NAME == "SecAgentHub"
    assert LogConfig.LEVEL == "INFO"
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
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && py -m pytest tests/test_harness_logging_core.py -v`
Expected: 5 passed

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_harness_logging_core.py
git commit -m "test: add core harness logging tests"
```

---

## 依赖关系

此计划完成后，可解锁以下计划：
- Plan 02: 敏感数据脱敏（独立，可并行）
- Plan 03: 错误码体系（独立，可并行）
- Plan 04: 日志聚合（依赖核心）
- Plan 05: AppException 集成（依赖错误码）
- Plan 06: AuditLogger（依赖核心）
- Plan 07: 代码迁移（依赖所有）
