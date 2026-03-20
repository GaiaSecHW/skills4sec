from tortoise import Tortoise
from app.config import settings


async def init_db():
    await Tortoise.init(
        db_url=settings.DATABASE_URL,
        modules={
            "models": [
                "app.models.user",
                "app.models.skill",
                "app.models.audit",
                "app.models.content",
                "app.models.login_log",
                "app.models.admin_log",
            ]
        },
    )
    # 生成数据库表结构
    await Tortoise.generate_schemas()


async def close_db():
    await Tortoise.close_connections()
