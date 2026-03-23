"""
用户 Repository - 用户数据访问
"""
from typing import Optional, List

from app.core.base_repository import BaseRepository
from app.models.user import User


class UserRepository(BaseRepository[User]):
    """用户数据访问层"""

    model_class = User

    async def find_by_employee_id(self, employee_id: str) -> Optional[User]:
        """通过工号查找用户"""
        return await self.model_class.get_or_none(employee_id=employee_id)

    async def count_by_status(self, status: str) -> int:
        """统计指定状态用户数"""
        return await self.model_class.filter(status=status).count()

    async def update_last_login(self, user: User) -> None:
        """更新最后登录时间"""
        from datetime import datetime, timezone
        user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
        await user.save(update_fields=["last_login"])
