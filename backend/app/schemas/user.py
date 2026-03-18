from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    email: EmailStr


class UserCreate(UserBase):
    """用户注册请求"""
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    """用户登录请求"""
    username: str
    password: str


class UserUpdate(BaseModel):
    """用户更新请求"""
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6, max_length=128)


class UserOut(BaseModel):
    """用户输出"""
    id: int
    username: str
    email: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    """Token 响应"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token 数据"""
    username: Optional[str] = None
