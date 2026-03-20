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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # 分页
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Gitea 配置 (用于技能提交)
    GITEA_API_URL: str = "http://172.28.95.77:3000/api/v1"
    GITEA_TOKEN: str = ""
    GITEA_REPO: str = "admin/skills4sec"  # owner/repo

    # 超级管理员配置
    SUPER_ADMIN_EMPLOYEE_ID: str = ""
    SUPER_ADMIN_API_KEY: str = ""
    SUPER_ADMIN_NAME: str = "系统管理员"

    # API 密钥安全配置
    API_KEY_MIN_LENGTH: int = 32

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
            ],
            "default_connection": "default",
        }
    },
}
