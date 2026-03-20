from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


# ============ 旧版 Schema（向后兼容） ============

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


# ============ 新版：工号登录相关 Schema ============

class UserLoginByEmployeeId(BaseModel):
    """工号+API密钥登录请求"""
    employee_id: str = Field(..., min_length=1, max_length=20, description="工号")
    api_key: str = Field(..., min_length=32, description="API密钥")


class UserCreateByAdmin(BaseModel):
    """管理员创建用户请求"""
    employee_id: str = Field(..., min_length=1, max_length=20, description="工号")
    name: str = Field(..., min_length=1, max_length=100, description="姓名")
    api_key: str = Field(..., min_length=32, description="API密钥")
    role: str = Field(default="user", pattern="^(user|admin|super_admin)$", description="角色")
    department: Optional[str] = Field(None, max_length=100, description="部门")
    team: Optional[str] = Field(None, max_length=100, description="团队")
    group_name: Optional[str] = Field(None, max_length=100, description="分组")


class UserUpdateByAdmin(BaseModel):
    """管理员更新用户请求"""
    name: Optional[str] = Field(None, max_length=100)
    api_key: Optional[str] = Field(None, min_length=32, description="留空则不修改")
    role: Optional[str] = Field(None, pattern="^(user|admin|super_admin)$")
    status: Optional[str] = Field(None, pattern="^(active|disabled)$")
    department: Optional[str] = Field(None, max_length=100)
    team: Optional[str] = Field(None, max_length=100)
    group_name: Optional[str] = Field(None, max_length=100)


class UserOutNew(BaseModel):
    """新用户输出（包含新字段）"""
    id: int
    employee_id: str
    name: Optional[str]
    role: str
    status: str
    department: Optional[str]
    team: Optional[str]
    group_name: Optional[str]
    skills_count: int
    last_login: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TokenWithRefresh(BaseModel):
    """带 Refresh Token 的响应"""
    success: bool = True
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800  # 30 minutes in seconds
    user: UserOutNew


class TokenRefresh(BaseModel):
    """刷新 Token 请求"""
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    """刷新 Token 响应"""
    success: bool = True
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1800
