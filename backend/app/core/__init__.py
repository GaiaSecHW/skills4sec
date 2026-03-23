"""
Core module - FastAPI + Tortoise-ORM 最佳实践组件
"""
from app.core.exceptions import (
    AppException,
    NotFoundError,
    ValidationError,
    UnauthorizedError,
    ForbiddenError,
    ConflictError,
    DatabaseError,
    register_exception_handlers,
)
from app.core.base_repository import BaseRepository
from app.core.logging import get_logger, setup_logging, RequestLoggingMiddleware
from app.core.database import (
    init_db,
    close_db,
    transaction,
    atomic,
    check_database_health,
    bulk_create,
    bulk_update,
)
from app.core.dependencies import (
    PaginationParams,
    get_pagination,
    get_current_user_dep,
    get_admin_user,
    get_super_admin,
    get_optional_user,
    get_repository,
)

__all__ = [
    # Exceptions
    "AppException",
    "NotFoundError",
    "ValidationError",
    "UnauthorizedError",
    "ForbiddenError",
    "ConflictError",
    "DatabaseError",
    "register_exception_handlers",
    # Repository
    "BaseRepository",
    # Logging
    "get_logger",
    "setup_logging",
    "RequestLoggingMiddleware",
    # Database
    "init_db",
    "close_db",
    "transaction",
    "atomic",
    "check_database_health",
    "bulk_create",
    "bulk_update",
    # Dependencies
    "PaginationParams",
    "get_pagination",
    "get_current_user_dep",
    "get_admin_user",
    "get_super_admin",
    "get_optional_user",
    "get_repository",
]
