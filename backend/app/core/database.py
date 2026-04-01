"""
数据库工具 - 事务管理和连接管理
"""
import functools
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, TypeVar, ParamSpec

from tortoise import Tortoise, connections
from tortoise.transactions import in_transaction

from app.config import settings
from app.core.exceptions import DatabaseError
from app.core.logging import get_logger

logger = get_logger("database")

P = ParamSpec("P")
T = TypeVar("T")


# ============ 数据库初始化 ============

async def init_db() -> None:
    """初始化数据库连接"""
    db_url = settings.DATABASE_URL

    # MySQL 连接池配置
    if db_url.startswith("mysql"):
        # 使用字典配置以支持连接池参数
        credentials = _parse_mysql_url(db_url)
        credentials["autocommit"] = True  # 自动提交，避免事务超时
        credentials["connect_timeout"] = 10  # 连接超时

        db_config = {
            "connections": {
                "default": {
                    "engine": "tortoise.backends.mysql",
                    "credentials": credentials,
                    "minsize": 1,
                    "maxsize": 10,
                    "recycle": 30,  # 每 30 秒回收连接，避免超时断开
                }
            },
            "apps": {
                "models": {
                    "models": [
                        "app.models.user",
                        "app.models.skill",
                        "app.models.audit",
                        "app.models.content",
                        "app.models.login_log",
                        "app.models.admin_log",
                        "app.models.submission",
                        "app.models.favorite",
                    ],
                    "default_connection": "default",
                }
            }
        }
        await Tortoise.init(config=db_config)
    else:
        # SQLite / PostgreSQL 使用默认配置
        await Tortoise.init(
            db_url=db_url,
            modules={
                "models": [
                    "app.models.user",
                    "app.models.skill",
                    "app.models.audit",
                    "app.models.content",
                    "app.models.login_log",
                    "app.models.admin_log",
                    "app.models.submission",
                    "app.models.favorite",
                ]
            },
        )
    await Tortoise.generate_schemas()
    logger.info(f'{{"event": "database_initialized", "url": "{settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "sqlite"}"}}')


def _parse_mysql_url(url: str) -> dict:
    """解析 MySQL URL 为字典格式

    mysql://user:password@host:port/database
    支持 URL 编码的特殊字符（如密码中的 @ 写成 %40）
    """
    import re
    from urllib.parse import unquote

    pattern = r"mysql://(?P<user>[^:]+):(?P<password>[^@]*)@(?P<host>[^:]+):(?P<port>\d+)/(?P<database>.+)"
    match = re.match(pattern, url)
    if not match:
        raise ValueError(f"Invalid MySQL URL: {url}")
    return {
        "host": match.group("host"),
        "port": int(match.group("port")),
        "user": unquote(match.group("user")),
        "password": unquote(match.group("password")),
        "database": unquote(match.group("database").strip()),
        "charset": "utf8mb4",
    }


async def close_db() -> None:
    """关闭数据库连接"""
    await Tortoise.close_connections()
    logger.info('{"event": "database_closed"}')


# ============ 事务管理 ============

@asynccontextmanager
async def transaction() -> AsyncGenerator:
    """
    事务上下文管理器

    Usage:
        async with transaction():
            await User.create(...)
            await Profile.create(...)
    """
    async with in_transaction() as conn:
        try:
            yield conn
        except Exception as e:
            logger.error(f'{{"event": "transaction_rollback", "error": "{str(e)}"}}')
            raise


def atomic(func: Callable[P, T]) -> Callable[P, T]:
    """
    事务装饰器

    Usage:
        @atomic
        async def create_user_with_profile(...):
            await User.create(...)
            await Profile.create(...)
    """
    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        async with in_transaction():
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f'{{"event": "atomic_rollback", "function": "{func.__name__}", "error": "{str(e)}"}}')
                raise
    return wrapper


# ============ 健康检查 ============

async def check_database_health() -> dict:
    """检查数据库连接状态"""
    try:
        conn = connections.get("default")
        await conn.execute_query("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected",
        }
    except Exception as e:
        logger.error(f'{{"event": "health_check_failed", "error": "{str(e)}"}}')
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
        }


# ============ 批量操作工具 ============

async def bulk_create(model_class, data_list: list, batch_size: int = 100) -> int:
    """
    批量创建记录

    Args:
        model_class: 模型类
        data_list: 数据字典列表
        batch_size: 批次大小

    Returns:
        创建的记录数
    """
    if not data_list:
        return 0

    total = 0
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i + batch_size]
        await model_class.bulk_create([model_class(**data) for data in batch])
        total += len(batch)

    logger.info(f'{{"event": "bulk_create", "model": "{model_class.__name__}", "count": {total}}}')
    return total


async def bulk_update(model_class, instances: list, fields: list, batch_size: int = 100) -> int:
    """
    批量更新记录

    Args:
        model_class: 模型类
        instances: 模型实例列表
        fields: 要更新的字段列表
        batch_size: 批次大小

    Returns:
        更新的记录数
    """
    if not instances:
        return 0

    total = 0
    for i in range(0, len(instances), batch_size):
        batch = instances[i:i + batch_size]
        await model_class.bulk_update(batch, fields)
        total += len(batch)

    logger.info(f'{{"event": "bulk_update", "model": "{model_class.__name__}", "count": {total}, "fields": {fields}}}')
    return total
