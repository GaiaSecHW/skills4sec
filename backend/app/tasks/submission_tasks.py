"""
提交相关定时任务 - 重试处理、状态同步、自动审核

迁移自 Gitea Actions，实现后台自动处理
"""
import asyncio
import json
import os
import re
import subprocess
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from app.models.submission import Submission, SubmissionEvent, SubmissionStatus, SubmissionEventType
from app.models.enums import RiskLevel
from app.core import get_logger
from app.config import settings

logger = get_logger("submission_tasks")

# ============ 预编译正则表达式 ============
# 用于解析仓库 URL，避免每次调用都重新编译
_TREE_PATTERN = re.compile(r'(https://[^/]+/[^/]+/[^/]+)/tree/([^/]+)(/.*)?')
_GITEA_PATTERN = re.compile(r'(https://[^/]+/[^/]+/[^/]+)/src/branch/([^/]+)(/.*)?')
_REPO_PATTERN = re.compile(r'https://[^/]+/[^/]+/[^/]+/?$')


# ============ 现有任务（保留） ============

async def process_pending_retries():
    """
    处理待重试的提交

    每30秒调用一次，检查需要重试的提交并执行重试
    """
    from app.services.retry_service import retry_service

    logger.debug("Checking pending retries...")
    results = await retry_service.process_pending_retries()

    if results["total"] > 0:
        logger.info(
            f"Retry task completed: {results['success']} success, "
            f"{results['failed']} failed, {results['skipped']} skipped"
        )

    return results


async def sync_gitea_status():
    """
    同步 Gitea Issue/PR 状态

    每5分钟调用一次，从 Gitea 同步最新的 Issue 和 PR 状态
    """
    from app.services.gitea_sync_service import gitea_sync_service

    logger.debug("Syncing Gitea status...")
    results = await gitea_sync_service.sync_all_pending()

    if results["total"] > 0:
        logger.info(
            f"Gitea sync completed: {results['total']} checked, "
            f"{results['updated']} updated, {results['errors']} errors"
        )

    return results


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

    每天调用一次，标记超过7天未更新的 processing 状态为 failed
    """
    stale_threshold = datetime.utcnow() - timedelta(days=7)

    # 查找卡在 processing 状态超过7天的提交
    stale_submissions = await Submission.filter(
        status=SubmissionStatus.PROCESSING,
        updated_at__lt=stale_threshold
    ).all()

    updated_count = 0
    for submission in stale_submissions:
        submission.status = SubmissionStatus.PROCESS_FAILED
        submission.error_message = "处理超时（超过7天未更新）"
        await submission.save()

        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.PROCESSING_FAILED,
            old_status=SubmissionStatus.PROCESSING,
            new_status=SubmissionStatus.PROCESS_FAILED,
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


# ============ 新增任务：自动审核流程 ============

async def process_new_submissions():
    """
    处理新的提交（从 Issue 或 API）

    每30秒调用一次：
    1. 轮询 Gitea Issue 中未处理的提交
    2. 克隆源仓库
    3. 发现 SKILL.md
    4. 创建 submission 记录
    5. 触发 AI 审计
    """
    from app.services.issue_handler import get_issue_handler

    issue_handler = get_issue_handler()
    issues = await issue_handler.list_unprocessed_issues(labels=["submission"])

    processed = 0
    errors = 0

    for issue in issues:
        try:
            issue_number = issue.get("number")
            issue_body = issue.get("body", "")
            issue_title = issue.get("title", "")

            # 解析源 URL
            source_url = issue_handler.parse_source_url(issue_body)
            if not source_url:
                await issue_handler.create_comment(
                    issue_number,
                    "❌ 无法解析源仓库 URL，请在 Issue 中提供正确的仓库地址。"
                )
                await issue_handler.close_issue(issue_number)
                errors += 1
                continue

            # 检查是否已存在 submission
            existing = await Submission.filter(source_url=source_url).first()
            if existing:
                await issue_handler.create_comment(
                    issue_number,
                    f"⚠️ 该技能已存在，状态：{existing.status}"
                )
                await issue_handler.close_issue(issue_number)
                continue

            # 通知正在处理
            skill_name = issue_title.replace("[提交技能]", "").strip()
            await issue_handler.notify_processing(issue_number, skill_name)

            # 克隆源仓库
            skill_dir, clone_error = await clone_skill_repo(source_url)
            if not skill_dir:
                await issue_handler.notify_rejected(
                    issue_number, skill_name, clone_error or "无法克隆源仓库"
                )
                errors += 1
                continue

            # 发现 SKILL.md
            skill_md = find_skill_md(skill_dir)
            if not skill_md:
                await issue_handler.notify_rejected(
                    issue_number, skill_name, "未找到 SKILL.md 文件"
                )
                shutil.rmtree(skill_dir, ignore_errors=True)
                errors += 1
                continue

            # 解析元数据
            metadata = parse_skill_metadata(skill_md)

            # 创建 submission 记录
            submission = await Submission.create(
                source_url=source_url,
                skill_name=metadata.get("name", skill_name),
                author=metadata.get("author", "unknown"),
                status=SubmissionStatus.PENDING_AUDIT,
                gitea_issue_number=issue_number,
                metadata=metadata,
            )

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.SUBMITTED,
                new_status=SubmissionStatus.PENDING_AUDIT,
                message="从 Issue 创建提交",
                triggered_by="issue_handler",
            )

            logger.info(f"Created submission {submission.id} from issue #{issue_number}")
            processed += 1

        except Exception as e:
            logger.error(f"Failed to process issue: {e}")
            errors += 1

    return {"processed": processed, "errors": errors}


async def run_security_audit():
    """
    执行 AI 安全审计

    每60秒调用一次：
    1. 查找 PENDING_AUDIT 状态的提交
    2. 调用 skill-report-generator 进行审计
    3. 根据审计结果自动处理：
       - safe/low → 自动合并到 skills/
       - medium/high → 标记需要人工审核
       - critical → 自动拒绝
    """
    from app.services.issue_handler import get_issue_handler
    from app.services.git_ops import get_git_ops

    # 查找待审计的提交
    pending_submissions = await Submission.filter(
        status=SubmissionStatus.PENDING_AUDIT
    ).limit(5).all()  # 每次最多处理5个

    processed = 0
    auto_approved = 0
    auto_rejected = 0
    needs_review = 0

    for submission in pending_submissions:
        try:
            # 更新状态为处理中
            submission.status = SubmissionStatus.PROCESSING
            await submission.save()

            # 克隆源仓库
            skill_dir, clone_error = await clone_skill_repo(submission.repo_url)
            if not skill_dir:
                submission.status = SubmissionStatus.AUDIT_FAILED
                submission.error_message = clone_error or "无法克隆源仓库"
                await submission.save()
                continue

            # 运行 AI 审计
            audit_result = await run_ai_audit(skill_dir, submission)

            if not audit_result:
                submission.status = SubmissionStatus.AUDIT_FAILED
                submission.error_message = "AI 审计失败"
                await submission.save()
                shutil.rmtree(skill_dir, ignore_errors=True)
                continue

            # 保存审计结果
            submission.audit_result = audit_result
            submission.risk_level = audit_result.get("risk_level", "unknown")

            issue_handler = get_issue_handler()
            git_ops = get_git_ops()

            risk_level = audit_result.get("risk_level", "unknown")

            if risk_level in ["safe", "low"]:
                # 自动批准
                await auto_approve_skill(submission, skill_dir, git_ops)
                await issue_handler.notify_approved(
                    submission.gitea_issue_number,
                    submission.skill_name,
                    audit_result.get("summary", ""),
                )
                auto_approved += 1

            elif risk_level in ["medium", "high"]:
                # 标记需要人工审核
                submission.status = SubmissionStatus.NEEDS_REVIEW
                await submission.save()
                await issue_handler.notify_needs_review(
                    submission.gitea_issue_number,
                    submission.skill_name,
                    audit_result.get("summary", ""),
                    risk_level,
                )
                needs_review += 1

            else:  # critical
                # 自动拒绝
                submission.status = SubmissionStatus.REJECTED
                submission.error_message = audit_result.get("summary", "安全风险过高")
                await submission.save()
                await issue_handler.notify_rejected(
                    submission.gitea_issue_number,
                    submission.skill_name,
                    "安全风险过高",
                    audit_result.get("critical_findings", []) +
                    audit_result.get("high_findings", []),
                )
                auto_rejected += 1

            # 清理临时目录
            shutil.rmtree(skill_dir, ignore_errors=True)
            processed += 1

        except Exception as e:
            logger.error(f"Failed to audit submission {submission.id}: {e}")
            submission.status = SubmissionStatus.AUDIT_FAILED
            submission.error_message = str(e)
            await submission.save()

    return {
        "processed": processed,
        "auto_approved": auto_approved,
        "auto_rejected": auto_rejected,
        "needs_review": needs_review,
    }



def parse_repo_url(source_url: str) -> tuple[str, str, str]:
    """
    解析仓库 URL，支持多种格式

    支持的格式：
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo
    - https://github.com/owner/repo/tree/main/skills/xxx
    - https://gitea.xxx.com/owner/repo/src/branch/main/skills/xxx

    Returns:
        (clone_url, branch, subdirectory)
    """
    clone_url = source_url
    branch = "main"
    subdir = ""

    # GitHub /tree/ 格式
    tree_match = _TREE_PATTERN.match(source_url)
    if tree_match:
        base_url = tree_match.group(1)
        branch = tree_match.group(2)
        subdir = tree_match.group(3).strip("/") if tree_match.group(3) else ""
        clone_url = f"{base_url}.git"
        return clone_url, branch, subdir

    # Gitea /src/branch/ 格式
    gitea_match = _GITEA_PATTERN.match(source_url)
    if gitea_match:
        base_url = gitea_match.group(1)
        branch = gitea_match.group(2)
        subdir = gitea_match.group(3).strip("/") if gitea_match.group(3) else ""
        clone_url = f"{base_url}.git"
        return clone_url, branch, subdir

    # 普通 git URL
    if source_url.endswith(".git"):
        return source_url, "main", ""

    # 没有 .git 后缀的仓库 URL
    if _REPO_PATTERN.match(source_url):
        return f"{source_url.rstrip('/')}.git", "main", ""

    return source_url, "main", ""


async def clone_skill_repo(source_url: str) -> tuple[Optional[str], str]:
    """
    克隆 skill 仓库到临时目录

    Returns:
        (临时目录路径, 错误信息) - 成功时错误信息为空字符串
    """
    try:
        temp_dir = tempfile.mkdtemp(prefix="skill_audit_")

        # 解析 URL
        clone_url, branch, subdir = parse_repo_url(source_url)

        # 处理 URL（添加 token 如果需要）
        if settings.GITEA_TOKEN and ("gitea" in clone_url or settings.GITEA_API_URL in clone_url):
            clone_url = clone_url.replace(
                "https://", f"https://oauth2:{settings.GITEA_TOKEN}@"
            )

        # 克隆仓库
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", branch, clone_url, temp_dir],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            logger.error(f"Git clone failed: {error_msg}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None, f"无法克隆仓库: {error_msg}"

        # 如果有子目录，返回子目录路径
        if subdir:
            skill_dir = os.path.join(temp_dir, subdir)
            if not os.path.exists(skill_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None, f"仓库中找不到子目录: {subdir}"
            return skill_dir, ""

        return temp_dir, ""

    except subprocess.TimeoutExpired:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, "克隆仓库超时"
    except Exception as e:
        logger.error(f"Failed to clone repo: {e}")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        return None, f"克隆仓库失败: {str(e)}"


def find_skill_md(skill_dir: str) -> Optional[Path]:
    """查找 SKILL.md 文件"""
    skill_path = Path(skill_dir)

    # 优先查找根目录
    skill_md = skill_path / "SKILL.md"
    if skill_md.exists():
        return skill_md

    # 递归查找
    for f in skill_path.rglob("SKILL.md"):
        if "node_modules" not in str(f) and ".git" not in str(f):
            return f

    return None


def parse_skill_metadata(skill_md: Path) -> Dict[str, Any]:
    """解析 SKILL.md 元数据"""
    import yaml

    try:
        content = skill_md.read_text(encoding="utf-8")
        metadata = {}

        if content.strip().startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                try:
                    metadata = yaml.safe_load(frontmatter) or {}
                except yaml.YAMLError:
                    pass

        return metadata

    except Exception as e:
        logger.error(f"Failed to parse skill metadata: {e}")
        return {}


async def run_ai_audit(skill_dir: str, submission: Submission) -> Optional[Dict]:
    """运行 AI 安全审计"""
    try:
        # 调用 skill-report-generator
        generator_path = Path(__file__).parent.parent.parent.parent / "skill-report-generator" / "generate.py"

        if not generator_path.exists():
            logger.error(f"Generator not found at {generator_path}")
            return None

        # 运行生成器
        result = subprocess.run(
            [
                "py", str(generator_path),
                "--input", skill_dir,
                "--dry-run",  # 不写入文件，只返回结果
            ],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(generator_path.parent),
        )

        if result.returncode != 0:
            logger.error(f"AI audit failed: {result.stderr}")
            return None

        # 解析输出中的 JSON
        # 由于是 dry-run 模式，需要从输出中提取报告
        output = result.stdout
        # 简单处理：查找 JSON 块
        import re
        json_match = re.search(r'\{[\s\S]*"security_audit"[\s\S]*\}', output)
        if json_match:
            try:
                # 需要找到完整的 JSON
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # 如果无法解析，返回默认安全结果
        return {
            "risk_level": "medium",
            "summary": "无法解析 AI 审计结果，需要人工审核",
        }

    except subprocess.TimeoutExpired:
        logger.error("AI audit timed out")
        return None
    except Exception as e:
        logger.error(f"Failed to run AI audit: {e}")
        return None


async def auto_approve_skill(
    submission: Submission,
    skill_dir: str,
    git_ops,
) -> bool:
    """自动批准 skill 并合并到仓库"""
    try:
        # 创建分支
        branch_name = f"auto-approve/{submission.author}/{submission.skill_name}"
        await git_ops.create_branch(branch_name)

        # 添加 skill 文件
        success, msg = await git_ops.add_skill_files(
            Path(skill_dir),
            "skills",
            submission.author,
            submission.skill_name,
        )

        if not success:
            logger.error(f"Failed to add skill files: {msg}")
            return False

        # 提交并推送
        commit_msg = f"feat: auto-approve skill {submission.skill_name} by {submission.author}"
        success, msg = await git_ops.commit_and_push(commit_msg)

        if not success:
            logger.error(f"Failed to commit: {msg}")
            return False

        # 合并到 main
        success, msg = await git_ops.merge_to_main(branch_name)

        if success:
            submission.status = SubmissionStatus.APPROVED
            await submission.save()

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.APPROVED,
                old_status=SubmissionStatus.PROCESSING,
                new_status=SubmissionStatus.APPROVED,
                message="AI 审计通过，自动批准",
                triggered_by="auto_auditor",
            )

            logger.info(f"Auto-approved skill: {submission.skill_name}")
            return True
        else:
            logger.error(f"Failed to merge: {msg}")
            return False

    except Exception as e:
        logger.error(f"Failed to auto-approve skill: {e}")
        return False


# ============ 任务调度配置 ============

TASK_SCHEDULE = {
    # 任务函数: (间隔秒数, 描述)
    process_pending_retries: (30, "处理待重试提交"),
    sync_gitea_status: (300, "同步 Gitea 状态"),
    cleanup_old_events: (3600, "清理过期事件日志"),
    cleanup_stale_submissions: (86400, "清理超时提交"),
    generate_daily_stats: (86400, "生成每日统计"),
    # 新增任务
    process_new_submissions: (30, "处理新提交"),
    run_security_audit: (60, "执行 AI 安全审计"),
}


def get_task_config():
    """获取任务配置"""
    return TASK_SCHEDULE
