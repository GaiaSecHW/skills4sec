# Harness Engineering 日志规范设计文档

> 创建日期: 2026-03-23
> 状态: 待审核

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
├── logging.py              # 保留（向后兼容）
└── harness_logging/
    ├── __init__.py         # 导出接口
    ├── config.py           # 日志配置
    ├── logger.py           # structlog 日志器封装
    ├── processors.py       # 自定义处理器
    │   ├── SensitiveFilter     # 敏感数据脱敏
    │   ├── HarnessFormatter    # Harness 格式化
    │   └── LogAggregator      # 日志聚合防刷屏
    ├── error_codes.py      # 错误码定义
    ├── middleware.py       # 请求日志中间件
    └── handlers.py         # 文件处理器

logs/
├── app.log                 # 全量应用日志
├── error.log               # 仅 ERROR 级别
├── access.log              # HTTP 请求日志
└── audit.log               # 审计日志（保留 90 天）
```

### 2.2 依赖

```
structlog>=24.1.0
loguru>=0.7.0
```

## 3. 日志格式

### 3.1 标准格式

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

### 3.2 ERROR 日志格式

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

### 3.3 Harness 兼容字段映射

| 字段 | 用途 | Harness 对应 |
|------|------|-------------|
| `trace_id` | 请求追踪 | `traceId` |
| `span_id` | 子操作标识 | `spanId` |
| `service` | 服务名 | `serviceName` |
| `event` | 事件类型 | 便于过滤查询 |
| `actor` | 操作人 | 审计追踪 |
| `business` | 业务 ID | 关联业务 |

## 4. 日志分类与轮转

### 4.1 分类配置

| 文件 | 用途 | 级别 | 保留天数 |
|------|------|------|---------|
| `app.log` | 全量应用日志 | DEBUG | 30 |
| `error.log` | 仅 ERROR 级别 | ERROR | 30 |
| `access.log` | HTTP 请求日志 | INFO | 30 |
| `audit.log` | 审计日志 | INFO | 90 |

### 4.2 轮转策略

- **按天轮转**：每天生成新文件
- **大小轮转**：单文件最大 50MB
- **压缩**：旧日志自动 gzip 压缩
- **清理**：超期日志自动删除

### 4.3 轮转效果示例

```
logs/
├── app.log                      # 当前日志
├── app.log.2026-03-22.gz        # 昨天日志（已压缩）
├── app.log.2026-03-21.gz
├── error.log
├── error.log.2026-03-22.gz
├── access.log
├── access.log.2026-03-22.gz
├── audit.log
├── audit.log.2026-03-22.gz
└── ...
```

## 5. 敏感数据脱敏

### 5.1 脱敏规则

| 数据类型 | 匹配规则 | 脱敏效果 |
|---------|---------|---------|
| API Key / Token | 字段名含 `api_key`, `token`, `secret`, `password` | `sk-a****cret` (首尾各4位) |
| 手机号 | 11位数字，1开头 | `138****5678` |
| 身份证号 | 18位数字/字母 | `310***********1234` |
| 邮箱 | `*@*.*` | `z***@example.com` |
| IP 地址 | IPv4 格式 | `192.168.*.*` |
| 银行卡号 | 16-19位数字 | `6222****1234` |
| 密码字段 | 字段名含 `pass`, `pwd`, `secret` | `******` |

### 5.2 脱敏示例

```python
# 输入
logger.info("用户登录", params={
    "api_key": "sk-abc123xyz789secret",
    "phone": "13812345678",
    "email": "zhangsan@example.com"
})

# 输出
{
  "params": {
    "api_key": "sk-a****cret",
    "phone": "138****5678",
    "email": "z***@example.com"
  }
}
```

## 6. 错误码体系

### 6.1 格式定义

`{模块}-{HTTP状态码}-{序号}`

### 6.2 模块前缀

| 前缀 | 模块 | 示例 |
|------|------|------|
| `AUTH` | 认证授权 | AUTH-401-01 |
| `USER` | 用户管理 | USER-404-01 |
| `SUBM` | 技能提交 | SUBM-500-01 |
| `SYNC` | Gitea 同步 | SYNC-503-01 |
| `SKILL` | 技能管理 | SKILL-409-01 |
| `ADMIN` | 管理后台 | ADMIN-403-01 |
| `SYS` | 系统内部 | SYS-500-01 |

### 6.3 错误码定义

```python
class ErrorCode:
    # AUTH 认证模块
    AUTH_401_01 = ("AUTH-401-01", "Token 已过期", "请重新登录")
    AUTH_401_02 = ("AUTH-401-02", "Token 无效", "Token 格式错误或被篡改")
    AUTH_401_03 = ("AUTH-401-03", "API Key 无效", "请检查 API Key 是否正确")
    AUTH_403_01 = ("AUTH-403-01", "权限不足", "需要管理员权限")
    AUTH_429_01 = ("AUTH-429-01", "登录失败次数过多", "账户已锁定 30 分钟")

    # USER 用户模块
    USER_404_01 = ("USER-404-01", "用户不存在", "请检查工号是否正确")
    USER_409_01 = ("USER-409-01", "工号已存在", "该工号已被注册")
    USER_400_01 = ("USER-400-01", "API Key 格式错误", "长度需至少 6 位")

    # SUBM 技能提交模块
    SUBM_400_01 = ("SUBM-400-01", "提交参数不完整", "缺少必填字段")
    SUBM_404_01 = ("SUBM-404-01", "提交记录不存在", "submission_id 无效")
    SUBM_409_01 = ("SUBM-409-01", "重复提交", "该技能已提交过")
    SUBM_500_01 = ("SUBM-500-01", "Issue 创建失败", "Gitea API 返回错误")

    # SYNC 同步模块
    SYNC_503_01 = ("SYNC-503-01", "Gitea API 超时", "服务无响应")
    SYNC_502_01 = ("SYNC-502-01", "Gitea API 错误", "上游服务返回异常")
    SYNC_401_01 = ("SYNC-401-01", "Gitea Token 无效", "请检查配置")

    # SYS 系统模块
    SYS_500_01 = ("SYS-500-01", "数据库连接失败", "请检查数据库状态")
    SYS_500_02 = ("SYS-500-02", "内部服务错误", "请联系管理员")
```

## 7. 日志聚合防刷屏

### 7.1 聚合策略

- **首次出现**：完整记录日志
- **重复出现**：计数累积，暂不输出
- **定时输出**：每分钟输出一次聚合日志

### 7.2 指纹计算

基于 `模块名 + 日志级别 + 事件类型 + 错误码` 计算 MD5 指纹。

### 7.3 聚合输出示例

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

### 7.4 配置

```python
class AggregatorConfig:
    ENABLED = True           # 是否启用
    WINDOW_SECONDS = 60      # 聚合窗口（秒）
    MAX_CACHE_SIZE = 1000    # 最大缓存条目
    SKIP_LEVELS = {"ERROR"}  # 跳过聚合的级别
```

## 8. API 设计

### 8.1 初始化

```python
# app/main.py
from app.core.harness_logging import setup_harness_logging

setup_harness_logging(
    level="DEBUG" if settings.DEBUG else "INFO",
    log_dir="logs",
    service_name="SecAgentHub",
)
```

### 8.2 HarnessLogger

```python
from app.core.harness_logging import HarnessLogger, ErrorCode

logger = HarnessLogger("submission")

# 最简调用
logger.info("处理完成")

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
logger.error(
    "Gitea Issue 创建失败",
    event="issue_create_failed",
    error_code=ErrorCode.SUBM_500_01,
    exception=e,
    root_cause="Gitea 服务返回 503",
)
```

### 8.3 AuditLogger

```python
from app.core.harness_logging import AuditLogger

audit = AuditLogger()

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

### 8.4 导出接口

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

## 9. 容错设计

### 9.1 设计原则

- 所有字段都可以省略
- 日志系统永不报错
- 自动填充上下文信息

### 9.2 自动填充

| 字段 | 来源 |
|------|------|
| `timestamp` | 自动生成 |
| `trace_id` | 中间件注入 / 自动生成 |
| `span_id` | 自动生成 |
| `service` | 配置项 |
| `actor` | 中间件注入 / 空对象 |
| `event` | 默认 `{module}_{level}` |

### 9.3 降级处理

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

## 10. 迁移计划

### 10.1 第一阶段：基础建设

1. 安装依赖：`structlog`, `loguru`
2. 创建 `app/core/harness_logging/` 模块
3. 实现核心组件
4. 更新 `main.py` 初始化

### 10.2 第二阶段：逐步迁移

1. 新代码直接使用 `HarnessLogger`
2. 旧代码按模块逐步迁移
3. 保留 `app/core/logging.py` 兼容层

### 10.3 第三阶段：清理

1. 移除旧日志模块
2. 统一使用新日志系统

---

## 附录：决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 日志分类 | 混合模式 | 职责清晰，便于运维 |
| 日志轮转 | 按天 + 大小 | 平衡存储与查询 |
| 敏感脱敏 | 增强脱敏 | 覆盖常见敏感数据 |
| 错误码 | 分层业务码 | 便于定位问题模块 |
| 防刷屏 | 采样聚合 | 保留信息，减少噪音 |
| 技术栈 | structlog + loguru | 功能强大，生态成熟 |
