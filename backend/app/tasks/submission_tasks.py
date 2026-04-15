"""
提交相关定时任务 - 清理过期数据
"""
import asyncio
from datetime import datetime, timedelta

from app.models.submission import Submission, SubmissionEvent, SubmissionStatus, SubmissionEventType
from app.core import get_logger

logger = get_logger("submission_tasks")


async def process_pending_retries():
    """
    处理待重试的提交

    每分钟调用一次，查找 next_retry_at 已过期且未达最大重试次数的提交
    """
    now = datetime.utcnow()

    retryable = await Submission.filter(
        next_retry_at__lte=now,
        retry_count__lt=3,
        status__in=[
            SubmissionStatus.ISSUE_FAILED,
            SubmissionStatus.PROCESS_FAILED,
        ],
    ).all()

    if not retryable:
        return {"retried": 0}

    retried = 0
    for submission in retryable:
        try:
            from app.services.workflow_service import workflow_service

            success, message = await workflow_service.start_workflow(submission)

            if success:
                submission.retry_count += 1
                submission.next_retry_at = None
                await submission.save()

                await SubmissionEvent.create(
                    submission=submission,
                    event_type=SubmissionEventType.RETRY_SUCCESS,
                    new_status=submission.status,
                    message=f"重试成功: {message}",
                    triggered_by="scheduler",
                )
            else:
                # 工作流再次失败，交由 retry_service 安排下次重试
                from app.services.retry_service import retry_service
                await retry_service.schedule_retry(submission, message)

            retried += 1
        except Exception as e:
            logger.exception(
                f"Retry failed for submission {submission.submission_id}: {e}",
            )

    if retried > 0:
        logger.info(f"Processed {retried} pending retries")

    return {"retried": retried}


async def sync_gitea_status():
    """
    从 Gitea 同步提交状态

    每5分钟调用一次，检查已创建 Issue/PR 的提交状态
    """
    from app.config import settings
    import httpx

    gitea_url = settings.GITEA_API_URL
    gitea_token = settings.GITEA_TOKEN
    gitea_repo = settings.GITEA_REPO

    if not gitea_token or not gitea_url:
        return {"synced": 0, "reason": "Gitea not configured"}

    # 查找有待同步状态的提交（有 issue_number 但未终态）
    active_submissions = await Submission.filter(
        issue_number__isnull=False,
        status__in=[
            SubmissionStatus.ISSUE_CREATED,
            SubmissionStatus.APPROVED,
            SubmissionStatus.PROCESSING,
            SubmissionStatus.PR_CREATED,
        ],
    ).limit(50).all()

    synced = 0
    async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=True, verify=False) as client:
        for sub in active_submissions:
            try:
                resp = await client.get(
                    f"{gitea_url}/repos/{gitea_repo}/issues/{sub.issue_number}",
                    headers={"Authorization": f"token {gitea_token}"},
                )
                if resp.status_code != 200:
                    continue

                issue_data = resp.json()
                issue_state = issue_data.get("state", "")

                labels = [l.get("name", "") for l in issue_data.get("labels", [])]

                old_status = sub.status

                if issue_state == "closed":
                    if "approved" in labels:
                        sub.status = SubmissionStatus.APPROVED
                    else:
                        sub.status = SubmissionStatus.REJECTED
                    await sub.save()

                    await SubmissionEvent.create(
                        submission=sub,
                        event_type=SubmissionEventType.STATUS_SYNCED,
                        old_status=old_status,
                        new_status=sub.status,
                        message=f"Gitea Issue #{sub.issue_number} 已关闭",
                        details={"issue_state": issue_state, "labels": labels},
                        triggered_by="scheduler",
                    )
                    synced += 1

            except Exception as e:
                logger.warning(f"Failed to sync submission {sub.submission_id}: {e}")

    if synced > 0:
        logger.info(f"Synced {synced} submission statuses from Gitea")

    return {"synced": synced}


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
                event_type=SubmissionEventType.RETRY_FAILED,
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
    process_pending_retries: (60, "处理待重试提交"),
    cleanup_old_events: (3600, "清理过期事件日志"),
    cleanup_stale_submissions: (86400, "清理超时提交"),
    generate_daily_stats: (86400, "生成每日统计"),
}


def get_task_config():
    """获取任务配置"""
    return TASK_SCHEDULE
