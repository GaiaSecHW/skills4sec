# Harness Logging - 敏感数据脱敏实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现敏感数据自动脱敏功能，覆盖 API Key、密码、手机号、身份证、邮箱、IP 等

**Architecture:** 正则匹配 + 字段名模式匹配 + 白名单机制，递归处理 dict/list/str 类型

**Tech Stack:** Python re, structlog>=23.1.0,<24.0.0

---

## Chunk 1: 敏感数据脱敏核心

### Task 1: 实现 processors.py - SensitiveFilter

**Files:**
- Create: `backend/app/core/harness_logging/processors.py`

- [ ] **Step 1: 编写脱敏处理器**

```python
# backend/app/core/harness_logging/processors.py
"""敏感数据脱敏处理器"""
import re
from typing import Any, Set, Tuple, Callable, Dict, List


# 白名单字段（不脱敏）
SKIP_MASK_FIELDS: Set[str] = {
    # 哈希值（已不可逆）
    "api_key_hash",
    "password_hash",
    "token_hash",
    "secret_hash",
    # 业务 ID（需要用于查询）
    "employee_id",
    "user_id",
    "submission_id",
    "skill_id",
    "audit_id",
    # 公开信息
    "name",
    "email_public",
    "public_email",
}

# 内容模式匹配规则 (pattern, replacement_func)
SENSITIVE_PATTERNS: List[Tuple[str, Callable[[re.Match], str]]] = [
    # 手机号：13812345678 -> 138****5678
    (
        r"1[3-9]\d{9}",
        lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:]
    ),
    # 身份证：310101199001011234 -> 310***********1234
    (
        r"\d{17}[\dXx]",
        lambda m: m.group(0)[:3] + "*" * 12 + m.group(0)[-4:]
    ),
    # 邮箱：zhangsan@example.com -> z***@example.com
    (
        r"[\w.-]+@[\w.-]+\.\w+",
        lambda m: m.group(0)[0] + "***@" + m.group(0).split("@")[1]
    ),
    # IPv4：192.168.1.100 -> 192.168.*.*
    (
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
        lambda m: ".".join(m.group(0).split(".")[:2]) + ".*.*"
    ),
    # 银行卡：6222021234567890123 -> 6222****0123
    (
        r"\d{16,19}",
        lambda m: m.group(0)[:4] + "****" + m.group(0)[-4:]
    ),
]

# 字段名匹配规则 (pattern, mask_func)
FIELD_NAME_PATTERNS: List[Tuple[str, Callable[[str], str]]] = [
    # API Key：保留首尾各4位
    (
        r"api_key",
        lambda v: v[:4] + "****" + v[-4:] if len(v) > 8 else "****"
    ),
    # Token（排除 hash）：保留首尾各4位
    (
        r"token(?!_hash)",
        lambda v: v[:4] + "****" + v[-4:] if len(v) > 8 else "****"
    ),
    # Secret（排除 hash）：全部脱敏
    (
        r"secret(?!_hash)",
        lambda v: "******"
    ),
    # Password（排除 hash）：全部脱敏
    (
        r"password(?!_hash)",
        lambda v: "******"
    ),
    # passwd
    (
        r"passwd",
        lambda v: "******"
    ),
    # pwd
    (
        r"pwd",
        lambda v: "******"
    ),
]


def mask_sensitive_data(data: dict) -> dict:
    """
    递归脱敏处理

    Args:
        data: 待脱敏的字典

    Returns:
        脱敏后的字典
    """
    if not isinstance(data, dict):
        return data

    def mask_value(key: str, value: Any) -> Any:
        # 跳过白名单
        if key in SKIP_MASK_FIELDS:
            return value

        # 处理字符串
        if isinstance(value, str):
            # 1. 字段名匹配
            for pattern, masker in FIELD_NAME_PATTERNS:
                if re.search(pattern, key, re.IGNORECASE):
                    try:
                        return masker(value)
                    except Exception:
                        return "****"

            # 2. 内容模式匹配
            for pattern, masker in SENSITIVE_PATTERNS:
                value = re.sub(pattern, masker, value)

        # 处理字典（递归）
        elif isinstance(value, dict):
            return {k: mask_value(k, v) for k, v in value.items()}

        # 处理列表（递归）
        elif isinstance(value, list):
            return [mask_value(key, item) for item in value]

        return value

    return {k: mask_value(k, v) for k, v in data.items()}
```

- [ ] **Step 2: 验证语法**

Run: `cd backend && py -c "from app.core.harness_logging.processors import mask_sensitive_data; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/harness_logging/processors.py
git commit -m "feat: add sensitive data masking processor"
```

---

## Chunk 2: 脱敏测试

### Task 2: 编写脱敏测试

**Files:**
- Create: `backend/tests/test_sensitive_masking.py`

- [ ] **Step 1: 编写测试**

```python
# backend/tests/test_sensitive_masking.py
"""敏感数据脱敏测试"""
import pytest
from app.core.harness_logging.processors import (
    mask_sensitive_data,
    SKIP_MASK_FIELDS,
)


class TestSensitiveMasking:
    """敏感数据脱敏测试"""

    def test_api_key_masking(self):
        """测试 API Key 脱敏"""
        data = {"api_key": "sk-abc123xyz789secret"}
        result = mask_sensitive_data(data)
        assert result["api_key"] == "sk-a****cret"

    def test_api_key_hash_not_masked(self):
        """测试 API Key Hash 不脱敏"""
        data = {"api_key_hash": "$2b$12$xxxxx"}
        result = mask_sensitive_data(data)
        assert result["api_key_hash"] == "$2b$12$xxxxx"

    def test_token_masking(self):
        """测试 Token 脱敏"""
        data = {"token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9abcdef"}
        result = mask_sensitive_data(data)
        assert result["token"] == "eyJh****fghij"

    def test_token_hash_not_masked(self):
        """测试 Token Hash 不脱敏"""
        data = {"token_hash": "abc123hash"}
        result = mask_sensitive_data(data)
        assert result["token_hash"] == "abc123hash"

    def test_password_masking(self):
        """测试密码脱敏"""
        data = {"password": "mysecretpassword"}
        result = mask_sensitive_data(data)
        assert result["password"] == "******"

    def test_password_hash_not_masked(self):
        """测试密码 Hash 不脱敏"""
        data = {"password_hash": "$2b$12$xxxxx"}
        result = mask_sensitive_data(data)
        assert result["password_hash"] == "$2b$12$xxxxx"

    def test_phone_masking(self):
        """测试手机号脱敏"""
        data = {"phone": "13812345678", "mobile": "13987654321"}
        result = mask_sensitive_data(data)
        assert result["phone"] == "138****5678"
        assert result["mobile"] == "139****4321"

    def test_id_card_masking(self):
        """测试身份证脱敏"""
        data = {"id_card": "310101199001011234"}
        result = mask_sensitive_data(data)
        assert result["id_card"] == "310***********1234"

    def test_email_masking(self):
        """测试邮箱脱敏"""
        data = {"email": "zhangsan@example.com"}
        result = mask_sensitive_data(data)
        assert result["email"] == "z***@example.com"

    def test_ip_masking(self):
        """测试 IP 地址脱敏"""
        data = {"ip": "192.168.1.100", "client_ip": "10.0.0.1"}
        result = mask_sensitive_data(data)
        assert result["ip"] == "192.168.*.*"
        assert result["client_ip"] == "10.0.*.*"

    def test_bank_card_masking(self):
        """测试银行卡脱敏"""
        data = {"bank_card": "6222021234567890123"}
        result = mask_sensitive_data(data)
        assert result["bank_card"] == "6222****0123"

    def test_whitelist_fields(self):
        """测试白名单字段不脱敏"""
        data = {
            "employee_id": "EMP001",
            "user_id": "USR123",
            "submission_id": "SUB-456",
            "name": "张三",
        }
        result = mask_sensitive_data(data)
        assert result["employee_id"] == "EMP001"
        assert result["user_id"] == "USR123"
        assert result["submission_id"] == "SUB-456"
        assert result["name"] == "张三"

    def test_nested_dict_masking(self):
        """测试嵌套字典脱敏"""
        data = {
            "user": {
                "name": "张三",
                "api_key": "sk-abc123xyz789secret",
                "contact": {
                    "phone": "13812345678",
                    "email": "zhangsan@example.com"
                }
            }
        }
        result = mask_sensitive_data(data)
        assert result["user"]["name"] == "张三"
        assert result["user"]["api_key"] == "sk-a****cret"
        assert result["user"]["contact"]["phone"] == "138****5678"
        assert result["user"]["contact"]["email"] == "z***@example.com"

    def test_list_masking(self):
        """测试列表脱敏"""
        data = {
            "users": [
                {"name": "张三", "phone": "13812345678"},
                {"name": "李四", "phone": "13987654321"}
            ]
        }
        result = mask_sensitive_data(data)
        assert result["users"][0]["phone"] == "138****5678"
        assert result["users"][1]["phone"] == "139****4321"

    def test_params_field_masking(self):
        """测试 params 字段脱敏（常见日志场景）"""
        data = {
            "params": {
                "api_key": "sk-live-abc123xyz789",
                "phone": "13812345678",
                "repo_url": "https://gitea.example.com/user/repo"
            }
        }
        result = mask_sensitive_data(data)
        assert result["params"]["api_key"] == "sk-l****xyz9"
        assert result["params"]["phone"] == "138****5678"
        assert result["params"]["repo_url"] == "https://gitea.example.com/user/repo"

    def test_non_dict_input(self):
        """测试非字典输入"""
        assert mask_sensitive_data("string") == "string"
        assert mask_sensitive_data(123) == 123
        assert mask_sensitive_data(None) is None
        assert mask_sensitive_data([]) == []
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && py -m pytest tests/test_sensitive_masking.py -v`
Expected: All tests passed (15+ tests)

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_sensitive_masking.py
git commit -m "test: add sensitive data masking tests"
```

---

## Chunk 3: 与 HarnessLogger 集成

### Task 3: 集成脱敏到 HarnessLogger

**Files:**
- Modify: `backend/app/core/harness_logging/logger.py`

- [ ] **Step 1: 添加脱敏导入**

```python
# backend/app/core/harness_logging/logger.py - 添加导入
from app.core.harness_logging.processors import mask_sensitive_data
```

- [ ] **Step 2: 修改 _log 方法添加脱敏**

```python
# 找到 _log 方法，修改为：
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
```

- [ ] **Step 3: 添加集成测试**

```python
# backend/tests/test_harness_logging_core.py - 添加测试
def test_harness_logger_with_sensitive_data():
    """测试日志器脱敏"""
    logger = HarnessLogger("test")
    logger.info(
        "user login",
        event="user_login",
        params={
            "api_key": "sk-live-abc123xyz789secret",
            "phone": "13812345678",
            "employee_id": "EMP001",  # 白名单，不脱敏
        },
    )
```

- [ ] **Step 4: 运行集成测试**

Run: `cd backend && py -m pytest tests/test_harness_logging_core.py::test_harness_logger_with_sensitive_data -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/harness_logging/logger.py
git add backend/tests/test_harness_logging_core.py
git commit -m "feat: integrate sensitive masking into HarnessLogger"
```

---

## Chunk 4: 更新导出接口

### Task 4: 更新 __init__.py 导出 mask_sensitive_data

**Files:**
- Modify: `backend/app/core/harness_logging/__init__.py`

- [ ] **Step 1: 更新导出**

```python
# backend/app/core/harness_logging/__init__.py - 添加导出
from app.core.harness_logging.processors import mask_sensitive_data

__all__ = [
    "HarnessLogger",
    "HarnessLoggingMiddleware",
    "LogConfig",
    "setup_harness_logging",
    "trace_id_ctx",
    "span_id_ctx",
    "actor_ctx",
    "request_id_ctx",  # 复用现有
    "mask_sensitive_data",  # 新增
]
```

- [ ] **Step 2: 验证导出**

Run: `cd backend && py -c "from app.core.harness_logging import mask_sensitive_data; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/harness_logging/__init__.py
git commit -m "feat: export mask_sensitive_data function"
```

---

## 依赖关系

此计划**独立**，可与 Plan 01 (核心基础设施) 并行执行，也可在 Plan 01 完成后执行。

此计划完成后，可解锁：
- Plan 07: 代码迁移（包含脱敏验证）
