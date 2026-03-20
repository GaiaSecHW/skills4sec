from fastapi import APIRouter, HTTPException, status, Depends, Request
from datetime import timedelta, datetime, timezone

from app.models.user import User
from app.models.login_log import LoginLog
from app.schemas.user import (
    UserLoginByEmployeeId, TokenWithRefresh, TokenRefresh,
    TokenRefreshResponse, UserOutNew
)
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    get_current_user,
    verify_api_key,
)
from app.config import settings

router = APIRouter(prefix="/auth", tags=["authentication"])


# ============ 认证接口（工号+API密钥） ============

@router.post("/login/new", response_model=TokenWithRefresh)
async def login_by_employee_id(
    request: Request,
    user_data: UserLoginByEmployeeId
):
    """
    工号 + API 密钥登录（新版）

    返回 JWT 访问令牌和刷新令牌。
    """
    # 获取客户端信息
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    # 查找用户
    user = await User.get_or_none(employee_id=user_data.employee_id)

    # 验证失败记录日志
    async def log_failure(reason: str):
        await LoginLog.create(
            employee_id=user_data.employee_id,
            status="failed",
            ip_address=client_ip,
            user_agent=user_agent,
            failure_reason=reason,
        )

    if not user:
        await log_failure("工号不存在")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="工号或 API 密钥错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 验证 API 密钥
    if not user.api_key_hash or not verify_api_key(user_data.api_key, user.api_key_hash):
        await log_failure("API 密钥错误")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="工号或 API 密钥错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != "active":
        await log_failure(f"用户状态异常: {user.status}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"用户已被{user.status}"
        )

    # 登录成功：更新最后登录时间
    user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
    await user.save()

    # 记录成功日志
    await LoginLog.create(
        employee_id=user.employee_id,
        status="success",
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # 创建令牌
    access_token = create_access_token(
        data={"sub": user.employee_id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_refresh_token(
        data={"sub": user.employee_id}
    )

    return TokenWithRefresh(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOutNew.model_validate(user),
    )


@router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(token_data: TokenRefresh):
    """
    刷新 Access Token

    使用有效的 Refresh Token 获取新的 Access Token。
    """
    employee_id = verify_refresh_token(token_data.refresh_token)
    if not employee_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 验证用户仍然有效
    user = await User.get_or_none(employee_id=employee_id)
    if not user or user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 创建新的 access token
    access_token = create_access_token(
        data={"sub": user.employee_id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return TokenRefreshResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ============ 用户信息接口 ============

@router.get("/me", response_model=UserOutNew)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户信息

    需要在请求头中携带有效的 JWT Token
    """
    return current_user
