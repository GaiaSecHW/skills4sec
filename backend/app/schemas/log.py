# backend/app/schemas/log.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LoginLogOut(BaseModel):
    """登录日志输出"""
    id: int
    employee_id: str
    login_time: datetime
    status: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    device_id: Optional[str]
    failure_reason: Optional[str]

    class Config:
        from_attributes = True


class AdminLogOut(BaseModel):
    """管理员操作日志输出"""
    id: int
    admin_id: int
    admin_employee_id: str
    action: str
    target_user_id: Optional[int]
    target_employee_id: Optional[str]
    details: Optional[dict]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
