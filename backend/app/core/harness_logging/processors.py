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