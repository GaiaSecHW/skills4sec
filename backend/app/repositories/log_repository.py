"""
日志 Repository - 登录日志和管理员日志数据访问
"""
from typing import Optional, List
from datetime import datetime

from app.core.base_repository import BaseRepository
from app.models.login_log import LoginLog
from app.models.admin_log import AdminLog


class LoginLogRepository(BaseRepository[LoginLog]):
    """登录日志数据访问层"""

    model_class = LoginLog

    async def find_by_employee_id(
        self,
        employee_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[LoginLog]:
        """按工号查询登录日志"""
        return await self.model_class.filter(
            employee_id__icontains=employee_id
        ).offset(skip).limit(limit).order_by("-login_time")

    async def find_failed_attempts(
        self,
        employee_id: str,
        since: datetime
    ) -> List[LoginLog]:
        """获取指定时间后的失败登录"""
        return await self.model_class.filter(
            employee_id=employee_id,
            status="failed",
            login_time__gte=since
        ).all()

    async def count_failed_attempts(
        self,
        employee_id: str,
        since: datetime
    ) -> int:
        """统计失败登录次数"""
        return await self.model_class.filter(
            employee_id=employee_id,
            status="failed",
            login_time__gte=since
        ).count()

    async def list_with_filters(
        self,
        skip: int = 0,
        limit: int = 50,
        employee_id: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[List[LoginLog], int]:
        """带筛选条件的列表查询"""
        query = self.model_class.all()

        if employee_id:
            query = query.filter(employee_id__icontains=employee_id)
        if status:
            query = query.filter(status=status)
        if start_date:
            query = query.filter(login_time__gte=start_date)
        if end_date:
            query = query.filter(login_time__lte=end_date)

        total = await query.count()
        logs = await query.offset(skip).limit(limit).order_by("-login_time")

        return logs, total


class AdminLogRepository(BaseRepository[AdminLog]):
    """管理员日志数据访问层"""

    model_class = AdminLog

    async def find_by_admin(
        self,
        admin_employee_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[AdminLog]:
        """按管理员工号查询"""
        return await self.model_class.filter(
            admin_employee_id__icontains=admin_employee_id
        ).offset(skip).limit(limit).order_by("-created_at")

    async def find_by_target(
        self,
        target_employee_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[AdminLog]:
        """按目标用户查询"""
        return await self.model_class.filter(
            target_employee_id__icontains=target_employee_id
        ).offset(skip).limit(limit).order_by("-created_at")

    async def list_with_filters(
        self,
        skip: int = 0,
        limit: int = 50,
        admin_employee_id: Optional[str] = None,
        action: Optional[str] = None,
        target_employee_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[List[AdminLog], int]:
        """带筛选条件的列表查询"""
        query = self.model_class.all()

        if admin_employee_id:
            query = query.filter(admin_employee_id__icontains=admin_employee_id)
        if action:
            query = query.filter(action__icontains=action)
        if target_employee_id:
            query = query.filter(target_employee_id__icontains=target_employee_id)
        if start_date:
            query = query.filter(created_at__gte=start_date)
        if end_date:
            query = query.filter(created_at__lte=end_date)

        total = await query.count()
        logs = await query.offset(skip).limit(limit).order_by("-created_at")

        return logs, total
