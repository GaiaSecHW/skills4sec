from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ============ 工号登录相关 Schema ============

class UserLoginByEmployeeId(BaseModel):
    """工号+API密钥登录请求"""
    employee_id: str = Field(..., min_length=1, max_length=20, description="工号")
    api_key: str = Field(..., min_length=6, description="API密钥")


class UserCreateByAdmin(BaseModel):
    """管理员创建用户请求"""
    employee_id: str = Field(..., min_length=1, max_length=20, description="工号")
    name: str = Field(..., min_length=1, max_length=100, description="姓名")
    api_key: str = Field(..., min_length=6, description="API密钥")
    role: str = Field(default="user", pattern="^(user|admin|super_admin)$", description="角色")
    department: Optional[str] = Field(None, max_length=100, description="部门")
    team: Optional[str] = Field(None, max_length=100, description="团队")
    group_name: Optional[str] = Field(None, max_length=100, description="分组")


class UserUpdateByAdmin(BaseModel):
    """管理员更新用户请求"""
    name: Optional[str] = Field(None, max_length=100)
    api_key: Optional[str] = Field(None, min_length=6, description="留空则不修改")
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
