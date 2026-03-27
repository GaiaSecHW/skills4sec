from datetime import datetime, timedelta
from typing import Optional
import re

from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from tortoise.exceptions import DoesNotExist

from app.config import settings
from app.models.user import User

# OAuth2 密码流
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8') if isinstance(hashed_password, str) else hashed_password
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT 访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


# ============ API 密钥相关函数 ============

def verify_api_key(plain_key: str, stored_key: str) -> bool:
    """验证 API 密钥（明文比较）"""
    return plain_key == stored_key


def validate_api_key_complexity(api_key: str) -> tuple[bool, str]:
    """验证 API 密钥复杂度"""
    if len(api_key) < settings.API_KEY_MIN_LENGTH:
        return False, f"API 密钥长度至少 {settings.API_KEY_MIN_LENGTH} 字符"

    # 检查是否包含常见弱密钥模式
    weak_patterns = ['123456', 'password', 'admin', 'qwerty', 'abcdef', '111111']
    api_key_lower = api_key.lower()
    for pattern in weak_patterns:
        if pattern in api_key_lower:
            return False, "API 密钥不能包含常见弱密钥模式"

    # 检查连续重复字符
    if re.search(r'(.)\1{3,}', api_key):
        return False, "API 密钥不能包含 4 个及以上连续相同字符"

    # 检查连续顺序字符
    if re.search(r'(0123|1234|2345|3456|4567|5678|6789|7890|abcd|bcde|cdef)', api_key_lower):
        return False, "API 密钥不能包含连续顺序字符"

    return True, ""


# ============ JWT Refresh Token 相关函数 ============

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT 刷新令牌"""
    to_encode = data.copy()
    to_encode.update({"type": "refresh"})  # 标记为 refresh token
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_refresh_token(token: str) -> Optional[str]:
    """验证刷新令牌，返回 employee_id 或 None"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return payload.get("sub")
    except JWTError:
        return None


# ============ 用户获取依赖 ============

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """获取当前登录用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub: str = payload.get("sub")
        if sub is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # 优先使用 employee_id 查找，兼容旧的 username
    user = await User.get_or_none(employee_id=sub)
    if not user:
        user = await User.get_or_none(username=sub)
    if not user:
        raise credentials_exception

    if getattr(user, 'status', 'active') != "active" and not user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")

    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """获取当前活跃用户"""
    if not current_user.is_active and getattr(current_user, 'status', 'active') != "active":
        raise HTTPException(status_code=400, detail="用户已被禁用")
    return current_user


async def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    """获取当前超级管理员"""
    if not current_user.is_superuser and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要管理员权限"
        )
    return current_user


# ============ 基于角色的权限校验 ============

async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """获取当前管理员用户（admin 或 super_admin）"""
    if getattr(current_user, 'role', 'user') not in ("admin", "super_admin") and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要管理员权限"
        )
    return current_user


async def get_current_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """获取当前超级管理员"""
    if getattr(current_user, 'role', 'user') != "super_admin" and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要超级管理员权限"
        )
    return current_user
