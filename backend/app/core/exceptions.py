"""
全局异常处理 - 统一错误响应格式
"""
from typing import Any, Optional
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """统一错误响应格式"""
    code: str
    message: str
    detail: Optional[Any] = None
    request_id: Optional[str] = None


class AppException(Exception):
    """应用基础异常"""
    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail: Optional[Any] = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.message)


class NotFoundError(AppException):
    """资源未找到"""
    def __init__(self, message: str = "资源未找到", detail: Optional[Any] = None):
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )


class ValidationError(AppException):
    """验证错误"""
    def __init__(self, message: str = "数据验证失败", detail: Optional[Any] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class UnauthorizedError(AppException):
    """未授权"""
    def __init__(self, message: str = "未授权访问", detail: Optional[Any] = None):
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )


class ForbiddenError(AppException):
    """禁止访问"""
    def __init__(self, message: str = "权限不足", detail: Optional[Any] = None):
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class ConflictError(AppException):
    """资源冲突"""
    def __init__(self, message: str = "资源已存在", detail: Optional[Any] = None):
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


class DatabaseError(AppException):
    """数据库错误"""
    def __init__(self, message: str = "数据库操作失败", detail: Optional[Any] = None):
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        )


# ============ 异常处理器 ============

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """处理自定义异常"""
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=exc.code,
            message=exc.message,
            detail=exc.detail,
            request_id=request_id,
        ).model_dump(exclude_none=True),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """处理 HTTP 异常"""
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code="HTTP_ERROR",
            message=str(exc.detail),
            request_id=request_id,
        ).model_dump(exclude_none=True),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理未知异常"""
    request_id = getattr(request.state, "request_id", None)
    # 生产环境不暴露详细错误
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            code="INTERNAL_ERROR",
            message="服务器内部错误",
            request_id=request_id,
        ).model_dump(exclude_none=True),
    )


def register_exception_handlers(app):
    """注册异常处理器"""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    # 生产环境可注释掉下面这行，避免暴露敏感信息
    # app.add_exception_handler(Exception, generic_exception_handler)
