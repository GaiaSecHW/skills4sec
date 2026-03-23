"""
Repository 基类 - 通用 CRUD 操作
"""
from typing import TypeVar, Generic, Type, Optional, List, Any
from abc import ABC

from tortoise.models import Model
from tortoise.queryset import QuerySet

from app.core.exceptions import NotFoundError, ConflictError
from app.core.logging import get_logger

logger = get_logger("repository")

ModelType = TypeVar("ModelType", bound=Model)


class BaseRepository(Generic[ModelType], ABC):
    """
    Repository 基类

    提供通用的 CRUD 操作，子类可以覆盖或扩展这些方法。

    Usage:
        class UserRepository(BaseRepository[User]):
            model_class = User

            async def find_by_employee_id(self, employee_id: str) -> Optional[User]:
                return await self.model_class.get_or_none(employee_id=employee_id)
    """

    model_class: Type[ModelType]

    def __init__(self):
        if not self.model_class:
            raise ValueError("model_class must be defined in subclass")

    @property
    def query(self) -> QuerySet[ModelType]:
        """获取基础查询集"""
        return self.model_class.all()

    # ============ 读取操作 ============

    async def get_by_id(self, id: int) -> ModelType:
        """通过 ID 获取，不存在则抛出异常"""
        instance = await self.model_class.get_or_none(id=id)
        if not instance:
            raise NotFoundError(
                message=f"{self.model_class.__name__} 不存在",
                detail={"id": id}
            )
        return instance

    async def get_by_id_or_none(self, id: int) -> Optional[ModelType]:
        """通过 ID 获取，不存在返回 None"""
        return await self.model_class.get_or_none(id=id)

    async def get_one(self, **filters) -> Optional[ModelType]:
        """获取单条记录"""
        return await self.model_class.filter(**filters).first()

    async def get_one_or_raise(self, **filters) -> ModelType:
        """获取单条记录，不存在则抛出异常"""
        instance = await self.get_one(**filters)
        if not instance:
            raise NotFoundError(
                message=f"{self.model_class.__name__} 不存在",
                detail=filters
            )
        return instance

    async def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: str = "-created_at",
        **filters
    ) -> List[ModelType]:
        """获取列表（分页）"""
        return await self.model_class.filter(**filters).offset(skip).limit(limit).order_by(order_by)

    async def count(self, **filters) -> int:
        """计数"""
        return await self.model_class.filter(**filters).count()

    async def exists(self, **filters) -> bool:
        """检查是否存在"""
        return await self.model_class.filter(**filters).exists()

    # ============ 写入操作 ============

    async def create(self, **data) -> ModelType:
        """创建记录"""
        instance = await self.model_class.create(**data)
        logger.info(f'{{"event": "create", "model": "{self.model_class.__name__}", "id": {instance.id}}}')
        return instance

    async def update(self, instance: ModelType, **data) -> ModelType:
        """更新记录"""
        for field, value in data.items():
            setattr(instance, field, value)
        await instance.save()
        logger.info(f'{{"event": "update", "model": "{self.model_class.__name__}", "id": {instance.id}}}')
        return instance

    async def update_by_id(self, id: int, **data) -> ModelType:
        """通过 ID 更新"""
        instance = await self.get_by_id(id)
        return await self.update(instance, **data)

    async def update_many(self, filters: dict, **data) -> int:
        """批量更新"""
        count = await self.model_class.filter(**filters).update(**data)
        logger.info(f'{{"event": "bulk_update", "model": "{self.model_class.__name__}", "count": {count}}}')
        return count

    async def delete(self, instance: ModelType) -> None:
        """删除记录"""
        await instance.delete()
        logger.info(f'{{"event": "delete", "model": "{self.model_class.__name__}", "id": {instance.id}}}')

    async def delete_by_id(self, id: int) -> None:
        """通过 ID 删除"""
        instance = await self.get_by_id(id)
        await self.delete(instance)

    async def delete_many(self, **filters) -> int:
        """批量删除"""
        count = await self.model_class.filter(**filters).delete()
        logger.info(f'{{"event": "bulk_delete", "model": "{self.model_class.__name__}", "count": {count}}}')
        return count

    # ============ 分页工具 ============

    async def paginate(
        self,
        page: int = 1,
        page_size: int = 20,
        order_by: str = "-created_at",
        **filters
    ) -> dict:
        """
        分页查询

        Returns:
            {
                "items": [...],
                "total": int,
                "page": int,
                "page_size": int,
                "total_pages": int,
            }
        """
        query = self.model_class.filter(**filters)
        total = await query.count()

        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        offset = (page - 1) * page_size

        items = await query.offset(offset).limit(page_size).order_by(order_by)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
