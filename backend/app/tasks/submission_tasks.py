"""
提交相关定时任务 - 清理过期数据
"""
import asyncio
from datetime import datetime, timedelta

from app.models.submission import Submission, SubmissionEvent, SubmissionStatus, SubmissionEventType
from app.core import get_logger

logger = get_logger("submission_tasks")


async def cleanup_old_events():
    """
    清理过期的事件日志

    每小时调用一次，删除90天前的事件日志
    """
    cutoff = datetime.utcnow() - timedelta(days=90)

    deleted = await SubmissionEvent.filter(created_at__lt=cutoff).delete()

    if deleted > 0:
        logger.info(f"Cleaned up {deleted} old submission events (older than 90 days)")

    return {"deleted": deleted}


async def cleanup_stale_submissions():
    """
    清理长时间未更新的提交

    每天调用一次，标记超过7天未更新的处理状态为 failed
    """
    stale_threshold = datetime.utcnow() - timedelta(days=7)

    # 查找卡在处理状态超过7天的提交
    processing_statuses = [
        SubmissionStatus.CLONING,
        SubmissionStatus.GENERATING,
    ]

    updated_count = 0
    for status_value in processing_statuses:
        stale_submissions = await Submission.filter(
            status=status_value,
            updated_at__lt=stale_threshold
        ).all()

        for submission in stale_submissions:
            submission.status = SubmissionStatus.FAILED
            submission.error_message = "处理超时（超过7天未更新）"
            await submission.save()

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.RETRY,
                old_status=status_value,
                new_status=SubmissionStatus.FAILED,
                message="系统标记为处理超时",
                triggered_by="scheduler"
            )
            updated_count += 1

    if updated_count > 0:
        logger.info(f"Marked {updated_count} stale submissions as failed")

    return {"updated": updated_count}


async def generate_daily_stats():
    """
    生成每日统计

    每天凌晨调用，生成前一天的统计数据并记录
    """
    from datetime import date

    yesterday = date.today() - timedelta(days=1)
    yesterday_start = datetime.combine(yesterday, datetime.min.time())
    yesterday_end = datetime.combine(yesterday, datetime.max.time())

    # 统计昨日提交
    total = await Submission.filter(
        created_at__gte=yesterday_start,
        created_at__lte=yesterday_end
    ).count()

    # 按状态统计
    by_status = {}
    for s in SubmissionStatus:
        count = await Submission.filter(
            status=s,
            created_at__gte=yesterday_start,
            created_at__lte=yesterday_end
        ).count()
        if count > 0:
            by_status[s.value] = count

    stats = {
        "date": yesterday.isoformat(),
        "total": total,
        "by_status": by_status
    }

    logger.info(f"Daily stats for {yesterday}: {stats}")
    return stats


# ============ 任务调度配置 ============

TASK_SCHEDULE = {
    # 任务函数: (间隔秒数, 描述)
    cleanup_old_events: (3600, "清理过期事件日志"),
    cleanup_stale_submissions: (86400, "清理超时提交"),
    generate_daily_stats: (86400, "生成每日统计"),
}


def get_task_config():
    """获取任务配置"""
    return TASK_SCHEDULE
