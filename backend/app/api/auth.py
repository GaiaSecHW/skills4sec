from fastapi import APIRouter, HTTPException, status, Depends
from datetime import timedelta

from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserOut, Token
from app.utils.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_superuser,
)
from app.config import settings

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """
    用户注册

    - **username**: 用户名 (3-64字符，仅字母数字下划线横线)
    - **email**: 邮箱地址
    - **password**: 密码 (6-128字符)
    """
    # 检查用户名是否已存在
    if await User.exists(username=user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已被注册"
        )

    # 检查邮箱是否已存在
    if await User.exists(email=user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被注册"
        )

    # 创建用户
    user = await User.create(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
    )

    return user


@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    """
    用户登录

    返回 JWT 访问令牌，用于后续 API 认证。
    在请求头中添加: `Authorization: Bearer <token>`
    """
    # 查找用户
    user = await User.get_or_none(username=user_data.username)

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户已被禁用"
        )

    # 创建访问令牌
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return Token(access_token=access_token)


@router.get("/me", response_model=UserOut)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户信息

    需要在请求头中携带有效的 JWT Token
    """
    return current_user


@router.patch("/me", response_model=UserOut)
async def update_current_user(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    更新当前用户信息

    可以更新邮箱和密码
    """
    if update_data.email:
        # 检查邮箱是否被其他用户使用
        if await User.exists(email=update_data.email, id__not=current_user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱已被其他用户使用"
            )
        current_user.email = update_data.email

    if update_data.password:
        current_user.hashed_password = get_password_hash(update_data.password)

    await current_user.save()
    return current_user


# ============ 管理员接口 ============

@router.get("/users", response_model=list[UserOut])
async def list_users(
    skip: int = 0,
    limit: int = 20,
    admin: User = Depends(get_current_superuser)
):
    """
    获取用户列表 (管理员)

    仅超级管理员可访问
    """
    users = await User.all().offset(skip).limit(limit).order_by("-created_at")
    return users


@router.patch("/users/{user_id}/deactivate", response_model=UserOut)
async def deactivate_user(
    user_id: int,
    admin: User = Depends(get_current_superuser)
):
    """
    禁用用户 (管理员)

    仅超级管理员可访问
    """
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能禁用超级管理员"
        )

    user.is_active = False
    await user.save()
    return user


@router.patch("/users/{user_id}/activate", response_model=UserOut)
async def activate_user(
    user_id: int,
    admin: User = Depends(get_current_superuser)
):
    """
    启用用户 (管理员)

    仅超级管理员可访问
    """
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.is_active = True
    await user.save()
    return user
