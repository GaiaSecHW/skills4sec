"""
数据库模块 - 向后兼容导出
"""
# 从 core 模块导出，保持向后兼容
from app.core.database import init_db, close_db, transaction, atomic

__all__ = ["init_db", "close_db", "transaction", "atomic"]
