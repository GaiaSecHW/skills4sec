from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "SecAgentHub API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # 数据库配置
    DATABASE_URL: str = "sqlite://db.sqlite3"
    # DATABASE_URL: str = "postgres://user:pass@localhost:5432/secagenthub"

    # JWT 配置
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 360  # 6小时

    # 分页
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Gitea 配置 (用于技能提交)
    # 通过 .env 配置: GITEA_API_URL=http://your-gitea:3000/api/v1
    GITEA_API_URL: str = ""
    GITEA_TOKEN: str = ""
    GITEA_REPO: str = ""  # owner/repo
    GITEA_SKILLS_BASE_URL: str = ""  # 技能仓库浏览地址

    # ICSL 组织同步配置 (用于与 icsl Gitea 组织双向同步 skill)
    ICSL_GITEA_API_URL: str = ""       # K8s 内部 Gitea API 地址
    ICSL_GITEA_TOKEN: str = ""         # icsl 组织 Token (需 org admin 权限)
    ICSL_ORG_NAME: str = "icsl"        # 组织名
    ICSL_SYNC_INTERVAL: int = 300      # 轮询间隔 (秒), 默认 5 分钟
    ICSL_SYNC_ON_STARTUP: bool = True  # Pod 启动时是否自动全量同步
    ICSL_DATA_DIR: str = "/data"       # PVC 持久化数据目录

    # 报告生成 API 配置 (用于技能报告生成)
    REPORT_API_KEY: str = ""
    REPORT_API_BASE_URL: str = "https://api.openai.com/v1"
    REPORT_API_MODEL: str = "gpt-4o"

    # 超级管理员配置
    SUPER_ADMIN_EMPLOYEE_ID: str = ""
    SUPER_ADMIN_API_KEY: str = ""
    SUPER_ADMIN_NAME: str = "系统管理员"

    # API 密钥安全配置
    API_KEY_MIN_LENGTH: int = 6

    # 登录安全配置
    MAX_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 30

    # Refresh Token 配置
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    class Config:
        env_file = ".env"


settings = Settings()

# Tortoise-ORM 配置 (用于 aerich)
TORTOISE_ORM = {
    "connections": {"default": settings.DATABASE_URL},
    "apps": {
        "models": {
            "models": [
                "app.models.user",
                "app.models.skill",
                "app.models.audit",
                "app.models.content",
                "app.models.login_log",
                "app.models.admin_log",
            ],
            "default_connection": "default",
        }
    },
}
