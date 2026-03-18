from enum import Enum


class RiskLevel(str, Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class SourceType(str, Enum):
    OFFICIAL = "official"
    COMMUNITY = "community"


class SupportedTool(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"
    CLAUDE_CODE = "claude-code"


class RiskFactor(str, Enum):
    SCRIPTS = "scripts"
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    ENV_ACCESS = "env_access"
    EXTERNAL_COMMANDS = "external_commands"
    CLOUD_API = "cloud_api"
    IAM = "iam"
