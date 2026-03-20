"""
任务调度器 - APScheduler 集成
"""
import logging
from typing import Callable, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# 全局调度器实例
scheduler = None


def setup_scheduler():
    """设置任务调度器"""
    global scheduler

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = AsyncIOScheduler()

        # 导入任务配置
        from app.tasks.submission_tasks import TASK_SCHEDULE

        # 注册所有定时任务
        for task_func, (interval_seconds, description) in TASK_SCHEDULE.items():
            scheduler.add_job(
                task_func,
                IntervalTrigger(seconds=interval_seconds),
                id=task_func.__name__,
                name=description,
                replace_existing=True,
                max_instances=1,  # 防止并发执行
                coalesce=True,    # 合并错过的执行
            )
            logger.info(f"Registered task: {task_func.__name__} (every {interval_seconds}s)")

        logger.info("Scheduler setup completed")
        return scheduler

    except ImportError:
        logger.warning("APScheduler not installed, scheduled tasks disabled")
        return None


def start_scheduler():
    """启动调度器"""
    global scheduler

    if scheduler:
        scheduler.start()
        logger.info("Scheduler started")
    else:
        logger.warning("Scheduler not available")


def shutdown_scheduler():
    """关闭调度器"""
    global scheduler

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown")


async def run_task_manually(task_name: str) -> Dict[str, Any]:
    """
    手动触发任务

    Args:
        task_name: 任务函数名

    Returns:
        任务执行结果
    """
    from app.tasks.submission_tasks import (
        process_pending_retries,
        sync_gitea_status,
        cleanup_old_events,
        cleanup_stale_submissions,
        generate_daily_stats,
    )

    tasks = {
        "process_pending_retries": process_pending_retries,
        "sync_gitea_status": sync_gitea_status,
        "cleanup_old_events": cleanup_old_events,
        "cleanup_stale_submissions": cleanup_stale_submissions,
        "generate_daily_stats": generate_daily_stats,
    }

    if task_name not in tasks:
        return {"success": False, "error": f"Unknown task: {task_name}"}

    task_func = tasks[task_name]

    try:
        logger.info(f"Manually running task: {task_name}")
        result = await task_func()
        return {
            "success": True,
            "task": task_name,
            "executed_at": datetime.utcnow().isoformat(),
            "result": result
        }
    except Exception as e:
        logger.exception(f"Task {task_name} failed")
        return {
            "success": False,
            "task": task_name,
            "error": str(e)
        }


def get_scheduler_status() -> Dict[str, Any]:
    """获取调度器状态"""
    global scheduler

    if not scheduler:
        return {
            "available": False,
            "running": False,
            "jobs": []
        }

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })

    return {
        "available": True,
        "running": scheduler.running,
        "jobs": jobs
    }
