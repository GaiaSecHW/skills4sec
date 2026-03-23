# 日志迁移指南

## 旧代码（logging.py）

```python
from app.core import get_logger

logger = get_logger("gitea_sync")
logger.info(f'{{"event": "issue_fetch_failed", "issue_number": {issue_number}}}')
```

## 新代码（HarnessLogger）

```python
from app.core.harness_logging import HarnessLogger

logger = HarnessLogger("sync")
logger.info(
    "Issue 获取失败",
    event="issue_fetch_failed",
    business={"issue_number": issue_number},
)
```

## 主要变化

| 旧 | 新 |
|---|---|
| `get_logger(name)` | `HarnessLogger(module)` |
| JSON 字符串内嵌 | 结构化字段 |
| `event` 在 JSON 内 | `event` 作为顶级字段 |
| 无错误码 | 可选 `error_code` 字段 |
| 无敏感数据脱敏 | 自动脱敏 |

## 字段映射

| 场景 | 旧字段 | 新字段 |
|------|--------|--------|
| 业务 ID | JSON 内 `submission_id` | `business={"submission_id": "..."}` |
| 请求参数 | JSON 内 `params` | `params={...}` |
| 操作人 | JSON 内 `actor` | `actor={...}` |
| 错误信息 | JSON 内 `error` | `error={...}` |
