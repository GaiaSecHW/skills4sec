# Harness Engineering 日志规范设计文档

> 创建日期: 2026-03-23
> 状态: 待审核
> 版本: v1.1

## 1. 概述

基于 Harness Engineering 最佳实践，重构后端日志系统，实现：
- 日志分类存储
- 结构化 JSON 格式（兼容 Harness Observability）
- 敏感数据自动脱敏
- 统一错误码体系
- 日志聚合防刷屏

## 2. 架构设计

### 2.1 目录结构

```
app/core/
├── logging.py              # 弃用（迁移后删除）
└── harness_logging/
    ├── __init__.py         # 导出接口
    ├── config.py           # 日志配置
    ├── logger.py           # structlog 日志器封装
    ├── processors.py       # 自定义处理器
    │   ├── SensitiveFilter     # 敏感数据脱敏
    │   ├── HarnessFormatter    # Harness 格式化
    │   └── LogAggregator      # 日志聚合防刷屏
    ├── error_codes.py      # 错误码定义
    ├── middleware.py       # 请求日志中间件（替换原 logging.py 中的）
    ├── handlers.py         # 文件处理器
    └── integration.py      # 与现有系统的集成

logs/
├── app.log                 # 全量应用日志
├── error.log               # 仅 ERROR 级别
├── access.log              # HTTP 请求日志
└── audit.log               # 审计日志（保留 90 天）
```

### 2.2 依赖

```
structlog>=23.1.0,<24.0.0   # 兼容 Python 3.10
loguru>=0.7.0
```

> **注意**: structlog 24.x 需要 Python 3.11+，项目使用 Python 3.10，故锁定 23.x 版本。

## 3. 与现有系统的兼容性

### 3.1 Trace ID 复用现有 request_id_ctx

新日志系统**复用**现有 `app/core/logging.py` 中的 `request_id_ctx`，而非重新定义：

```python
# app/core/harness_logging/middleware.py
from app.core.logging import request_id_ctx  # 复用现有上下文变量

class HarnessLoggingMiddleware:
    """请求日志中间件 - 替换原 RequestLoggingMiddleware"""

    async def dispatch(self, request, call_next):
        # 复用现有的 request_id 生成逻辑
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:12]
        request_id_ctx.set(request_id)
        request.state.request_id = request_id

        # 设置新日志系统的上下文
        log_context.set({
            "trace_id": request_id,  # 直接复用
            "span_id": str(uuid.uuid4())[:8],
            "actor": self._extract_actor(request),
        })

        return await call_next(request)
```

**字段映射**：
- `trace_id` = 现有 `request_id`（用于跨服务追踪）
- `span_id` = 新增（用于同一请求内的子操作标识）

### 3.2 与现有异常体系集成

现有 `app/core/exceptions.py` 的 `AppException` 需要添加 `error_code` 字段：

```python
# app/core/exceptions.py (修改)
class AppException(Exception):
    """应用异常基类"""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        code: str = "INTERNAL_ERROR",  # 现有字段
        error_code: str = None,        # 新增：分层业务码
        detail: dict = None,
        suggestion: str = None,        # 新增：解决建议
    ):
        self.message = message
        self.status_code = status_code
        self.code = code
        self.error_code = error_code or f"SYS-{status_code}-01"
        self.detail = detail or {}
        self.suggestion = suggestion
        super().__init__(message)
```

**异常处理器集成**：

```python
# app/core/exceptions.py (修改)
from app.core.harness_logging import HarnessLogger

logger = HarnessLogger("exception")

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    # 自动记录结构化错误日志
    logger.error(
        exc.message,
        event="exception_raised",
        error_code=exc.error_code,
        status_code=exc.status_code,
        detail=exc.detail,
        suggestion=exc.suggestion,
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "code": exc.code,
            "error_code": exc.error_code,
            "detail": exc.detail,
            "suggestion": exc.suggestion,
        }
    )
```

### 3.3 AuditLogger 与现有审计模型的关系

**双轨审计策略**：

| 方式 | 存储 | 用途 | 保留期限 |
|------|------|------|---------|
| `AuditLogger` | `logs/audit.log` | 离线分析、合规审计 | 90 天 |
| 数据库模型 (`AuditLog`, `SubmissionEvent`) | MySQL | 实时查询、业务展示 | 永久 |

**使用场景**：
- 用户登录/登出 → 同时写入两者
- 数据变更操作 → 同时写入两者
- 内部系统操作 → 仅写入 `audit.log`

**实现**：

```python
# app/core/harness_logging/audit.py
class AuditLogger:
    def __init__(self):
        self.file_logger = HarnessLogger("audit")
        # 可选：同时写入数据库

    async def log(self, action: str, actor: dict, target: dict, result: str, details: dict = None):
        # 1. 写入文件日志
        self.file_logger.info(
            f"Audit: {action}",
            event=f"audit_{action}",
            actor=actor,
            target=target,
            result=result,
            details=details,
        )

        # 2. 可选：写入数据库
        if self._should_persist_to_db(action):
            await self._persist_to_db(action, actor, target, result, details)
```

## 4. 日志格式

### 4.1 标准格式

```json
{
  "timestamp": "2026-03-23T14:30:45.123Z",
  "service": "SecAgentHub",
  "level": "INFO",
  "trace_id": "abc123def456",
  "span_id": "req-001",
  "module": "submission",
  "message": "技能提交创建成功",
  "event": "submission_created",
  "actor": {
    "employee_id": "EMP001",
    "name": "张三"
  },
  "business": {
    "submission_id": "sub-abc123",
    "skill_name": "SQL注入检测"
  },
  "params": {
    "repo_url": "https://gitea.example.com/...",
    "category": "security"
  },
  "error": null,
  "duration_ms": 156.78
}
```

### 4.2 ERROR 日志格式

```json
{
  "level": "ERROR",
  "message": "Gitea Issue 创建失败",
  "event": "issue_create_failed",
  "error": {
    "code": "SUBM-500-01",
    "message": "Issue 创建失败",
    "type": "TimeoutException",
    "stack_trace": "Traceback (most recent call last):\n  ...",
    "root_cause": "Gitea 服务无响应，连接超时 30s"
  }
}
```

### 4.3 Harness 兼容字段映射

| 字段 | 用途 | Harness 对应 |
|------|------|-------------|
| `trace_id` | 请求追踪 | `traceId` |
| `span_id` | 子操作标识 | `spanId` |
| `service` | 服务名 | `serviceName` |
| `event` | 事件类型 | 便于过滤查询 |
| `actor` | 操作人 | 审计追踪 |
| `business` | 业务 ID | 关联业务 |

## 5. 日志分类与轮转

### 5.1 分类配置

| 文件 | 用途 | 级别 | 保留天数 |
|------|------|------|---------|
| `app.log` | 全量应用日志 | DEBUG | 30 |
| `error.log` | 仅 ERROR 级别 | ERROR | 30 |
| `access.log` | HTTP 请求日志 | INFO | 30 |
| `audit.log` | 审计日志 | INFO | 90 |

### 5.2 轮转策略

loguru 的 `rotation` 参数支持多种方式，但不支持同时使用。采用以下策略：

```python
# handlers.py
from loguru import logger

def setup_file_handlers(config: LogConfig):
    for name, handler in config.HANDLERS.items():
        logger.add(
            sink=f"{config.LOG_DIR}/{handler['filename']}",
            level=handler["level"],
            # 按大小轮转（达到 50MB 时切割）
            rotation="50 MB",
            # 按时间保留（超过 N 天删除）
            retention=f"{handler['retention_days']} days",
            compression="gz",
            serialize=True,  # JSON 格式
            enqueue=True,    # 异步写入，避免阻塞
        )
```

**轮转效果**：

```
logs/
├── app.log                      # 当前日志
├── app.log.2026-03-23_14-30-00_123456.gz  # 按大小切割后压缩
├── error.log
├── access.log
└── audit.log
```

> **注意**: loguru 不支持"按天+大小"双重轮转，实际使用"按大小轮转 + 按时间保留"策略。

## 6. 敏感数据脱敏

### 6.1 脱敏规则

| 数据类型 | 匹配规则 | 脱敏效果 |
|---------|---------|---------|
| API Key / Token | 字段名含 `api_key`, `token`, `secret` | `sk-a****cret` (首尾各4位) |
| 密码字段 | 字段名含 `password`, `passwd`, `pwd` | `******` |
| 手机号 | 11位数字，1开头 | `138****5678` |
| 身份证号 | 18位数字/字母 | `310***********1234` |
| 邮箱 | `*@*.*` | `z***@example.com` |
| IP 地址 | IPv4 格式 | `192.168.*.*` |
| 银行卡号 | 16-19位数字 | `6222****1234` |
| JWT Token | `Authorization` 头 | `Bearer eyJ****xyz` |

### 6.2 白名单（不脱敏）

以下字段**不进行脱敏**：

```python
SKIP_MASK_FIELDS = {
    # 哈希值（已不可逆）
    "api_key_hash",
    "password_hash",
    "token_hash",
    # 业务 ID（需要用于查询）
    "employee_id",
    "user_id",
    "submission_id",
    # 公开信息
    "name",
    "email_public",
}
```

### 6.3 脱敏实现

```python
# processors.py
import re
from typing import Any, Set

SKIP_MASK_FIELDS: Set[str] = {
    "api_key_hash", "password_hash", "token_hash",
    "employee_id", "user_id", "submission_id",
    "name", "email_public",
}

SENSITIVE_PATTERNS = [
    # 手机号
    (r"1[3-9]\d{9}", lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:]),
    # 身份证
    (r"\d{17}[\dXx]", lambda m: m.group(0)[:3] + "*" * 12 + m.group(0)[-4:]),
    # 邮箱
    (r"[\w.-]+@[\w.-]+\.\w+", lambda m: m.group(0)[0] + "***@" + m.group(0).split("@")[1]),
    # IPv4
    (r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", lambda m: ".".join(m.group(0).split(".")[:2]) + ".*.*"),
    # 银行卡
    (r"\d{16,19}", lambda m: m.group(0)[:4] + "****" + m.group(0)[-4:]),
]

FIELD_NAME_PATTERNS = [
    (r"api_key", lambda v: v[:4] + "****" + v[-4:] if len(v) > 8 else "****"),
    (r"token(?!_hash)", lambda v: v[:4] + "****" + v[-4:] if len(v) > 8 else "****"),
    (r"secret(?!_hash)", lambda v: "******"),
    (r"password(?!_hash|_hash)", lambda v: "******"),
    (r"passwd", lambda v: "******"),
    (r"pwd", lambda v: "******"),
]

def mask_sensitive_data(data: dict) -> dict:
    """递归脱敏处理"""
    def mask_value(key: str, value: Any) -> Any:
        # 跳过白名单
        if key in SKIP_MASK_FIELDS:
            return value

        if isinstance(value, str):
            # 字段名匹配
            for pattern, masker in FIELD_NAME_PATTERNS:
                if re.search(pattern, key, re.IGNORECASE):
                    try:
                        return masker(value)
                    except Exception:
                        return "****"

            # 内容模式匹配
            for pattern, masker in SENSITIVE_PATTERNS:
                value = re.sub(pattern, masker, value)

        elif isinstance(value, dict):
            return {k: mask_value(k, v) for k, v in value.items()}

        elif isinstance(value, list):
            return [mask_value(key, item) for item in value]

        return value

    return {k: mask_value(k, v) for k, v in data.items()}
```

### 6.4 脱敏示例

```python
# 输入
logger.info("用户登录", params={
    "api_key": "sk-abc123xyz789secret",
    "api_key_hash": "$2b$12$xxxxx",  # 不脱敏
    "phone": "13812345678",
    "email": "zhangsan@example.com",
    "employee_id": "EMP001",  # 不脱敏
})

# 输出
{
  "params": {
    "api_key": "sk-a****cret",
    "api_key_hash": "$2b$12$xxxxx",
    "phone": "138****5678",
    "email": "z***@example.com",
    "employee_id": "EMP001"
  }
}
```

## 7. 错误码体系

### 7.1 格式定义

`{模块}-{HTTP状态码}-{序号}`

### 7.2 模块前缀

| 前缀 | 模块 | 示例 |
|------|------|------|
| `AUTH` | 认证授权 | AUTH-401-01 |
| `USER` | 用户管理 | USER-404-01 |
| `SUBM` | 技能提交 | SUBM-500-01 |
| `SYNC` | Gitea 同步 | SYNC-503-01 |
| `SKILL` | 技能管理 | SKILL-409-01 |
| `ADMIN` | 管理后台 | ADMIN-403-01 |
| `SYS` | 系统内部 | SYS-500-01 |

### 7.3 错误码定义

```python
# error_codes.py
from typing import Tuple

class ErrorCode:
    """错误码定义: (code, message, suggestion)"""

    # ========== AUTH 认证模块 ==========
    AUTH_401_01 = ("AUTH-401-01", "Token 已过期", "请重新登录")
    AUTH_401_02 = ("AUTH-401-02", "Token 无效", "Token 格式错误或被篡改")
    AUTH_401_03 = ("AUTH-401-03", "API Key 无效", "请检查 API Key 是否正确")
    AUTH_403_01 = ("AUTH-403-01", "权限不足", "需要管理员权限")
    AUTH_429_01 = ("AUTH-429-01", "登录失败次数过多", "账户已锁定 30 分钟")

    # ========== USER 用户模块 ==========
    USER_404_01 = ("USER-404-01", "用户不存在", "请检查工号是否正确")
    USER_409_01 = ("USER-409-01", "工号已存在", "该工号已被注册")
    USER_400_01 = ("USER-400-01", "API Key 格式错误", "长度需至少 6 位")

    # ========== SUBM 技能提交模块 ==========
    SUBM_400_01 = ("SUBM-400-01", "提交参数不完整", "缺少必填字段")
    SUBM_404_01 = ("SUBM-404-01", "提交记录不存在", "submission_id 无效")
    SUBM_409_01 = ("SUBM-409-01", "重复提交", "该技能已提交过")
    SUBM_500_01 = ("SUBM-500-01", "Issue 创建失败", "Gitea API 返回错误")

    # ========== SYNC 同步模块 ==========
    SYNC_503_01 = ("SYNC-503-01", "Gitea API 超时", "服务无响应")
    SYNC_502_01 = ("SYNC-502-01", "Gitea API 错误", "上游服务返回异常")
    SYNC_401_01 = ("SYNC-401-01", "Gitea Token 无效", "请检查配置")

    # ========== SYS 系统模块 ==========
    SYS_500_01 = ("SYS-500-01", "数据库连接失败", "请检查数据库状态")
    SYS_500_02 = ("SYS-500-02", "内部服务错误", "请联系管理员")

    @classmethod
    def get(cls, code: str) -> Tuple[str, str, str]:
        """获取错误码详情"""
        return getattr(cls, code, (code, "未知错误", ""))
```

### 7.4 与 AppException 集成

```python
# 使用示例
from app.core.exceptions import NotFoundError
from app.core.harness_logging import ErrorCode

# 方式1：直接使用错误码
raise NotFoundError(
    message="用户不存在",
    error_code=ErrorCode.USER_404_01[0],
    suggestion=ErrorCode.USER_404_01[2],
)

# 方式2：异常处理器自动记录
# 见 3.2 节的 app_exception_handler
```

## 8. 日志聚合防刷屏

### 8.1 聚合策略

- **首次出现**：完整记录日志
- **重复出现**：计数累积，暂不输出
- **定时输出**：每分钟输出一次聚合日志

### 8.2 异步实现方案

使用 `asyncio` 后台任务 + 内存缓存，**仅在单进程模式下启用**：

```python
# processors.py
import asyncio
import hashlib
from collections import defaultdict
from datetime import datetime
from typing import Dict, Optional

class LogAggregator:
    """日志聚合器 - 单进程模式"""

    def __init__(self, window_seconds: int = 60, max_cache: int = 1000):
        self.window_seconds = window_seconds
        self.max_cache = max_cache
        self._cache: Dict[str, dict] = defaultdict(lambda: {
            "count": 0,
            "first_seen": None,
            "last_seen": None,
            "record": None,
        })
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._output_callback = None

    async def start(self, output_callback):
        """启动后台聚合任务"""
        self._output_callback = output_callback
        self._task = asyncio.create_task(self._flush_loop())

    async def stop(self):
        """停止聚合任务"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def compute_fingerprint(self, record: dict) -> str:
        """计算日志指纹"""
        key = f"{record.get('module')}:{record.get('level')}:{record.get('event')}:{record.get('error', {}).get('code', '')}"
        return hashlib.md5(key.encode()).hexdigest()[:16]

    async def process(self, record: dict) -> Optional[dict]:
        """处理日志记录，返回 None 表示暂不输出"""
        # ERROR 级别不聚合
        if record.get("level") == "ERROR":
            return record

        fingerprint = self.compute_fingerprint(record)

        async with self._lock:
            cache_entry = self._cache[fingerprint]
            cache_entry["count"] += 1
            cache_entry["last_seen"] = datetime.utcnow()

            if cache_entry["count"] == 1:
                # 首次出现
                cache_entry["first_seen"] = datetime.utcnow()
                cache_entry["record"] = record
                return record
            else:
                # 重复出现，暂不输出
                return None

    async def _flush_loop(self):
        """定时输出聚合日志"""
        while True:
            await asyncio.sleep(self.window_seconds)
            await self._flush()

    async def _flush(self):
        """输出所有聚合日志"""
        async with self._lock:
            for fingerprint, entry in self._cache.items():
                if entry["count"] > 1:
                    # 输出聚合日志
                    aggregated = {
                        **entry["record"],
                        "aggregate": {
                            "count": entry["count"],
                            "first_seen": entry["first_seen"].isoformat() + "Z",
                            "last_seen": entry["last_seen"].isoformat() + "Z",
                            "duration_seconds": self.window_seconds,
                        }
                    }
                    await self._output_callback(aggregated)

            # 清空缓存
            self._cache.clear()
```

### 8.3 多 Worker 部署说明

**问题**：多 Worker 模式下，每个 Worker 有独立的聚合缓存，无法共享状态。

**解决方案**：

```python
# config.py
class AggregatorConfig:
    ENABLED = True
    # 单 Worker 模式：使用内存聚合
    # 多 Worker 模式：禁用聚合或使用 Redis
    MODE = "memory"  # memory | redis | disabled

    # Redis 配置（可选）
    REDIS_URL = None
```

**建议**：
- 开发环境：启用内存聚合
- 生产环境（单 Worker）：启用内存聚合
- 生产环境（多 Worker）：禁用聚合或使用 Redis

### 8.4 聚合输出示例

```json
{
  "timestamp": "2026-03-23T14:31:00.000Z",
  "level": "WARN",
  "message": "Gitea API 超时",
  "event": "gitea_timeout",
  "aggregate": {
    "count": 47,
    "first_seen": "2026-03-23T14:30:45.123Z",
    "last_seen": "2026-03-23T14:30:59.876Z",
    "duration_seconds": 60
  }
}
```

## 9. API 设计

### 9.1 初始化

```python
# app/main.py
from app.core.harness_logging import setup_harness_logging

# 替换原有的 setup_logging
setup_harness_logging(
    level="DEBUG" if settings.DEBUG else "INFO",
    log_dir="logs",
    service_name="SecAgentHub",
    enable_aggregation=True,  # 生产环境多 Worker 时设为 False
)
```

### 9.2 HarnessLogger

```python
from app.core.harness_logging import HarnessLogger, ErrorCode

logger = HarnessLogger("submission")

# 最简调用（所有字段可选）
logger.info("处理完成")
# 输出: {"message": "处理完成", "event": "submission_info", ...}

# 部分字段
logger.info("创建成功", event="created", business={"id": "123"})

# 完整调用
logger.info(
    "技能提交创建成功",
    event="submission_created",
    actor={"employee_id": "EMP001", "name": "张三"},
    business={"submission_id": "sub-abc123", "skill_name": "SQL注入检测"},
    params={"category": "security"},
)

# 错误日志
try:
    ...
except Exception as e:
    logger.error(
        "Gitea Issue 创建失败",
        event="issue_create_failed",
        error_code=ErrorCode.SUBM_500_01[0],
        exception=e,  # 自动捕获堆栈
        root_cause="Gitea 服务返回 503",
    )
```

### 9.3 AuditLogger

```python
from app.core.harness_logging import AuditLogger

audit = AuditLogger()

# 审计日志
audit.log(
    action="user_login",
    actor={"employee_id": "EMP001", "name": "张三", "ip": "192.168.1.100"},
    target={"type": "user", "id": "EMP001"},
    result="success",
    details={"method": "api_key"},
)

audit.log(
    action="skill_approved",
    actor={"employee_id": "ADMIN01", "name": "管理员"},
    target={"type": "submission", "id": "sub-abc123"},
    result="success",
    details={"skill_name": "SQL注入检测", "issue_number": 42},
)
```

### 9.4 导出接口

```python
# app/core/harness_logging/__init__.py
from .logger import HarnessLogger, AuditLogger
from .config import LogConfig, setup_harness_logging
from .error_codes import ErrorCode
from .processors import mask_sensitive_data

__all__ = [
    "HarnessLogger",
    "AuditLogger",
    "ErrorCode",
    "LogConfig",
    "setup_harness_logging",
    "mask_sensitive_data",
]
```

## 10. 容错设计

### 10.1 设计原则

- 所有字段都可以省略
- 日志系统永不报错
- 自动填充上下文信息

### 10.2 自动填充

| 字段 | 来源 |
|------|------|
| `timestamp` | 自动生成 |
| `trace_id` | 复用现有 `request_id_ctx` |
| `span_id` | 自动生成 |
| `service` | 配置项 |
| `actor` | 中间件注入 / 空对象 |
| `event` | 默认 `{module}_{level}` |

### 10.3 降级处理

```python
def _log(self, level: str, message: str, **kwargs):
    try:
        record = self._build_record(message, level, **kwargs)
        record = mask_sensitive_data(record)
        record = self._aggregate(record)
        self._output(level, record)
    except Exception as e:
        # 日志系统自身出错，降级到标准输出
        sys.stderr.write(f"[LOG_ERROR] {e}\n")
```

## 11. 迁移计划

### 11.1 第一阶段：基础建设（1-2 天）

1. 安装依赖：`structlog>=23.1.0,<24.0.0`, `loguru>=0.7.0`
2. 创建 `app/core/harness_logging/` 模块
3. 实现核心组件
4. 修改 `AppException` 添加 `error_code` 字段
5. 更新 `main.py` 初始化

### 11.2 第二阶段：逐步迁移（3-5 天）

1. 新代码直接使用 `HarnessLogger`
2. 旧代码按模块逐步迁移：
   - `gitea_sync_service.py`
   - `retry_service.py`
   - `scheduler.py`
   - API 路由层
3. 替换 `RequestLoggingMiddleware` 为新的 `HarnessLoggingMiddleware`

### 11.3 第三阶段：清理（1 天）

1. 删除 `app/core/logging.py`
2. 统一使用新日志系统
3. 更新文档

### 11.4 迁移代码示例

**迁移前**（现有代码）：

```python
from app.core import get_logger

logger = get_logger("gitea_sync")
logger.info(f'{{"event": "issue_fetch_failed", "issue_number": {issue_number}}}')
```

**迁移后**：

```python
from app.core.harness_logging import HarnessLogger

logger = HarnessLogger("sync")  # 使用新模块名
logger.info(
    "Issue 获取失败",
    event="issue_fetch_failed",
    business={"issue_number": issue_number},
)
```

---

## 附录 A：决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 日志分类 | 混合模式 | 职责清晰，便于运维 |
| 日志轮转 | 按大小 + 时间保留 | loguru 限制，实际可行 |
| 敏感脱敏 | 增强脱敏 + 白名单 | 覆盖常见敏感数据，避免误脱敏 |
| 错误码 | 分层业务码 | 便于定位问题模块 |
| 防刷屏 | 内存聚合（单进程） | 简单可靠，多 Worker 可禁用 |
| 技术栈 | structlog 23.x + loguru | 兼容 Python 3.10 |
| Trace ID | 复用现有 request_id_ctx | 避免重复定义，保持兼容 |

## 附录 B：性能考虑

1. **异步写入**：loguru 的 `enqueue=True` 确保文件写入不阻塞请求
2. **聚合内存**：最大 1000 条目，约 1MB 内存占用
3. **脱敏开销**：正则匹配在大量数据时有一定开销，可通过配置禁用

## 附录 C：动态日志级别

支持通过配置或 API 动态调整日志级别：

```python
# 方式1：配置文件
LOG_LEVEL=DEBUG py -m uvicorn app.main:app

# 方式2：API（需实现）
POST /admin/log-level
{"level": "DEBUG"}
```

## 附录 D：测试策略

```python
# tests/test_harness_logging.py

def test_sensitive_mask():
    """测试敏感数据脱敏"""
    data = {"api_key": "sk-abc123xyz789secret", "phone": "13812345678"}
    masked = mask_sensitive_data(data)
    assert masked["api_key"] == "sk-a****cret"
    assert masked["phone"] == "138****5678"

def test_error_code_integration():
    """测试错误码与异常集成"""
    exc = NotFoundError(message="用户不存在", error_code="USER-404-01")
    assert exc.error_code == "USER-404-01"

async def test_aggregator():
    """测试日志聚合"""
    aggregator = LogAggregator(window_seconds=1)
    # ... 测试聚合逻辑
```
