"""
技能数据加载器 - 统一 skills.json 读取与缓存

所有模块通过此服务读取 skills.json，避免重复实现和缓存不一致。
"""
import json
import os
import re
import asyncio
from typing import Optional, Dict, List

from app.core.logging import get_logger

logger = get_logger("skill_loader")

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
SKILLS_JSON_PATH = os.path.join(_PROJECT_ROOT, "docs", "data", "skills.json")
DOWNLOAD_STATS_PATH = os.path.join(_PROJECT_ROOT, "docs", "data", "download_stats.json")

# skills.json 缓存
_skills_cache: Optional[list] = None
_skills_mtime: float = 0

# 下载计数异步锁（协程安全）
_stats_lock = asyncio.Lock()

# slug 合法性验证: 只允许小写字母、数字、连字符
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$")


def validate_slug(slug: str) -> bool:
    """验证 slug 格式，防止路径遍历攻击"""
    return bool(SLUG_PATTERN.match(slug))


def load_skills_json() -> list:
    """读取 skills.json，带 mtime 文件缓存"""
    global _skills_cache, _skills_mtime
    try:
        mtime = os.path.getmtime(SKILLS_JSON_PATH)
        if _skills_cache is not None and mtime == _skills_mtime:
            return _skills_cache
        with open(SKILLS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _skills_cache = data
        _skills_mtime = mtime
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def find_skill_by_slug(slug: str) -> Optional[dict]:
    """根据 slug 查找技能"""
    for item in load_skills_json():
        if item.get("slug") == slug:
            return item
    return None


def load_download_stats() -> Dict[str, int]:
    """读取下载计数"""
    try:
        with open(DOWNLOAD_STATS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_download_stats(stats: Dict[str, int]):
    """保存下载计数"""
    os.makedirs(os.path.dirname(DOWNLOAD_STATS_PATH), exist_ok=True)
    with open(DOWNLOAD_STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


async def increment_download(slug: str):
    """递增下载计数（异步锁，协程安全）"""
    async with _stats_lock:
        stats = load_download_stats()
        stats[slug] = stats.get(slug, 0) + 1
        _save_download_stats(stats)
