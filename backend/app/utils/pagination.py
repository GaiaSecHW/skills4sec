from typing import TypeVar, Generic, List
from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """通用分页响应"""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def calculate_pagination(total: int, page: int, page_size: int) -> dict:
    """计算分页信息"""
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    offset = (page - 1) * page_size
    return {
        "total_pages": total_pages,
        "offset": offset,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
