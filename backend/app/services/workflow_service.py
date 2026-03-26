"""
工作流服务 - 执行技能提交的三步工作流

步骤：
1. 克隆仓库 → backend/skills_download/{author}/{repo}/
2. 生成报告 → 执行 skill-report-generator/generate.py
3. 迁移文件 → skills/{author}/{skill-name}/
"""
import asyncio
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from app.models.submission import (
    Submission,
    SubmissionEvent,
    SubmissionStatus,
    SubmissionEventType
)
from app.config import settings
from app.core import get_logger

logger = get_logger("workflow_service")


class WorkflowStep:
    """工作流步骤常量"""
    CLONING = "cloning"
    GENERATING = "generating"
    MIGRATING = "migrating"
    COMPLETED = "completed"


class WorkflowService:
    """工作流服务"""

    # 目录配置
    DOWNLOAD_DIR = Path(__file__).parent.parent.parent / "skills_download"
    SKILLS_DIR = Path(__file__).parent.parent.parent.parent / "skills"

    # 生成器路径
    GENERATOR_PATH = Path(__file__).parent.parent.parent.parent / "skill-report-generator" / "generate.py"

    def __init__(self):
        # 确保目录存在
        self.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    async def start_workflow(self, submission: Submission) -> Tuple[bool, str]:
        """
        启动完整工作流

        Args:
            submission: 提交记录

        Returns:
            (是否成功, 消息)
        """
        logger.info(f"Starting workflow for submission {submission.submission_id}")

        # 更新状态为克隆中
        submission.status = SubmissionStatus.CLONING
        submission.current_step = WorkflowStep.CLONING
        submission.processing_started_at = datetime.utcnow()
        submission.step_details = {}
        await submission.save()

        # 记录事件
        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.CLONE_STARTED,
            new_status=SubmissionStatus.CLONING,
            message="工作流已启动，开始克隆仓库",
            triggered_by="workflow_service"
        )

        # 步骤 1: 克隆仓库
        success, message, local_path = await self.clone_repo(submission)
        if not success:
            return False, message

        # 步骤 2: 生成报告
        success, message = await self.generate_report(submission, local_path)
        if not success:
            return False, message

        # 步骤 3: 迁移文件
        success, message = await self.migrate_files(submission, local_path)
        if not success:
            return False, message

        # 完成
        submission.status = SubmissionStatus.COMPLETED
        submission.current_step = WorkflowStep.COMPLETED
        submission.processing_completed_at = datetime.utcnow()
        submission.completed_at = datetime.utcnow()
        await submission.save()

        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.COMPLETED,
            new_status=SubmissionStatus.COMPLETED,
            message="工作流完成",
            triggered_by="workflow_service"
        )

        logger.info(f"Workflow completed for submission {submission.submission_id}")
        return True, "工作流完成"

    async def execute_step(
        self,
        submission: Submission,
        step: str,
        local_path: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        执行单个步骤

        Args:
            submission: 提交记录
            step: 步骤名称 (cloning/generating/migrating)
            local_path: 本地路径（用于 generating 和 migrating）

        Returns:
            (是否成功, 消息)
        """
        if step == WorkflowStep.CLONING:
            return await self.clone_repo(submission)
        elif step == WorkflowStep.GENERATING:
            if not local_path:
                # 从 step_details 获取路径
                local_path = submission.step_details.get("cloning", {}).get("local_path")
            if not local_path:
                return False, "缺少本地路径信息"
            return await self.generate_report(submission, local_path)
        elif step == WorkflowStep.MIGRATING:
            if not local_path:
                local_path = submission.step_details.get("cloning", {}).get("local_path")
            if not local_path:
                return False, "缺少本地路径信息"
            return await self.migrate_files(submission, local_path)
        else:
            return False, f"未知步骤: {step}"

    async def clone_repo(self, submission: Submission) -> Tuple[bool, str, Optional[str]]:
        """
        克隆仓库

        Returns:
            (是否成功, 消息, 本地路径)
        """
        start_time = time.time()
        logger.info(f"Cloning repo: {submission.repo_url}")

        # 更新状态
        submission.status = SubmissionStatus.CLONING
        submission.current_step = WorkflowStep.CLONING
        await submission.save()

        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.CLONE_STARTED,
            message=f"开始克隆: {submission.repo_url}",
            triggered_by="workflow_service"
        )

        try:
            # 解析 author 和 repo
            author, repo = self._parse_repo_url(submission.repo_url)

            # 创建目标目录
            local_path = self.DOWNLOAD_DIR / author / repo
            if local_path.exists():
                shutil.rmtree(local_path, ignore_errors=True)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # 执行 git clone
            result = subprocess.run(
                ["git", "clone", "--depth", "1", submission.repo_url, str(local_path)],
                capture_output=True,
                text=True,
                timeout=120
            )

            duration = time.time() - start_time

            if result.returncode != 0:
                error_msg = f"克隆失败: {result.stderr[:500]}"
                logger.error(error_msg)

                submission.status = SubmissionStatus.FAILED
                submission.error_message = error_msg
                submission.step_details["cloning"] = {
                    "status": "failed",
                    "error": error_msg,
                    "duration": duration
                }
                await submission.save()

                await SubmissionEvent.create(
                    submission=submission,
                    event_type=SubmissionEventType.CLONE_FAILED,
                    message=error_msg,
                    error_message=error_msg,
                    triggered_by="workflow_service"
                )

                return False, error_msg, None

            # 成功
            logger.info(f"Clone completed in {duration:.2f}s")

            submission.step_details["cloning"] = {
                "status": "completed",
                "local_path": str(local_path),
                "author": author,
                "repo": repo,
                "duration": duration
            }
            await submission.save()

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.CLONE_SUCCESS,
                message=f"克隆完成 ({duration:.2f}s)",
                details={"local_path": str(local_path), "duration": duration},
                triggered_by="workflow_service"
            )

            return True, f"克隆完成 ({duration:.2f}s)", str(local_path)

        except subprocess.TimeoutExpired:
            error_msg = "克隆超时（超过120秒）"
            logger.error(error_msg)

            submission.status = SubmissionStatus.FAILED
            submission.error_message = error_msg
            submission.step_details["cloning"] = {"status": "failed", "error": error_msg}
            await submission.save()

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.CLONE_FAILED,
                message=error_msg,
                error_message=error_msg,
                triggered_by="workflow_service"
            )

            return False, error_msg, None

        except Exception as e:
            error_msg = f"克隆异常: {str(e)}"
            logger.exception(error_msg)

            submission.status = SubmissionStatus.FAILED
            submission.error_message = error_msg
            submission.step_details["cloning"] = {"status": "failed", "error": error_msg}
            await submission.save()

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.CLONE_FAILED,
                message=error_msg,
                error_message=error_msg,
                triggered_by="workflow_service"
            )

            return False, error_msg, None

    async def generate_report(
        self,
        submission: Submission,
        local_path: str
    ) -> Tuple[bool, str]:
        """
        生成审计报告

        Args:
            submission: 提交记录
            local_path: 本地仓库路径

        Returns:
            (是否成功, 消息)
        """
        start_time = time.time()
        logger.info(f"Generating report for: {local_path}")

        # 更新状态
        submission.status = SubmissionStatus.GENERATING
        submission.current_step = WorkflowStep.GENERATING
        await submission.save()

        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.GENERATE_STARTED,
            message="开始生成报告",
            triggered_by="workflow_service"
        )

        try:
            # 检查生成器是否存在
            if not self.GENERATOR_PATH.exists():
                raise FileNotFoundError(f"生成器不存在: {self.GENERATOR_PATH}")

            # 执行生成器
            result = subprocess.run(
                ["py", str(self.GENERATOR_PATH), "--input", local_path],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(self.GENERATOR_PATH.parent)
            )

            duration = time.time() - start_time

            if result.returncode != 0:
                error_msg = f"生成报告失败: {result.stderr[:500]}"
                logger.error(error_msg)

                submission.status = SubmissionStatus.FAILED
                submission.error_message = error_msg
                submission.step_details["generating"] = {
                    "status": "failed",
                    "error": error_msg,
                    "duration": duration
                }
                await submission.save()

                await SubmissionEvent.create(
                    submission=submission,
                    event_type=SubmissionEventType.GENERATE_FAILED,
                    message=error_msg,
                    error_message=error_msg,
                    triggered_by="workflow_service"
                )

                return False, error_msg

            # 检查报告文件是否生成
            report_path = Path(local_path) / "skill-report.json"
            if not report_path.exists():
                error_msg = "报告文件未生成: skill-report.json"
                logger.error(error_msg)

                submission.status = SubmissionStatus.FAILED
                submission.error_message = error_msg
                submission.step_details["generating"] = {
                    "status": "failed",
                    "error": error_msg,
                    "duration": duration
                }
                await submission.save()

                await SubmissionEvent.create(
                    submission=submission,
                    event_type=SubmissionEventType.GENERATE_FAILED,
                    message=error_msg,
                    error_message=error_msg,
                    triggered_by="workflow_service"
                )

                return False, error_msg

            # 成功
            logger.info(f"Report generated in {duration:.2f}s")

            submission.step_details["generating"] = {
                "status": "completed",
                "report_path": str(report_path),
                "duration": duration
            }
            await submission.save()

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.GENERATE_SUCCESS,
                message=f"报告生成完成 ({duration:.2f}s)",
                details={"report_path": str(report_path), "duration": duration},
                triggered_by="workflow_service"
            )

            return True, f"报告生成完成 ({duration:.2f}s)"

        except subprocess.TimeoutExpired:
            error_msg = "生成报告超时（超过300秒）"
            logger.error(error_msg)

            submission.status = SubmissionStatus.FAILED
            submission.error_message = error_msg
            submission.step_details["generating"] = {"status": "failed", "error": error_msg}
            await submission.save()

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.GENERATE_FAILED,
                message=error_msg,
                error_message=error_msg,
                triggered_by="workflow_service"
            )

            return False, error_msg

        except Exception as e:
            error_msg = f"生成报告异常: {str(e)}"
            logger.exception(error_msg)

            submission.status = SubmissionStatus.FAILED
            submission.error_message = error_msg
            submission.step_details["generating"] = {"status": "failed", "error": error_msg}
            await submission.save()

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.GENERATE_FAILED,
                message=error_msg,
                error_message=error_msg,
                triggered_by="workflow_service"
            )

            return False, error_msg

    async def migrate_files(
        self,
        submission: Submission,
        local_path: str
    ) -> Tuple[bool, str]:
        """
        迁移文件到目标目录

        Args:
            submission: 提交记录
            local_path: 本地仓库路径

        Returns:
            (是否成功, 消息)
        """
        start_time = time.time()
        logger.info(f"Migrating files from: {local_path}")

        # 更新状态
        submission.status = SubmissionStatus.MIGRATING
        submission.current_step = WorkflowStep.MIGRATING
        await submission.save()

        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.MIGRATE_STARTED,
            message="开始迁移文件",
            triggered_by="workflow_service"
        )

        try:
            # 从 step_details 获取 author 和 repo
            cloning_info = submission.step_details.get("cloning", {})
            author = cloning_info.get("author", "unknown")
            repo = cloning_info.get("repo", "unknown")

            # 目标目录
            target_path = self.SKILLS_DIR / author / repo

            # 如果目标已存在，先删除
            if target_path.exists():
                shutil.rmtree(target_path, ignore_errors=True)

            # 创建目标目录
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 复制整个目录
            shutil.copytree(local_path, target_path)

            duration = time.time() - start_time
            logger.info(f"Files migrated in {duration:.2f}s to {target_path}")

            submission.step_details["migrating"] = {
                "status": "completed",
                "target_path": str(target_path),
                "duration": duration
            }
            await submission.save()

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.MIGRATE_SUCCESS,
                message=f"文件迁移完成 ({duration:.2f}s)",
                details={"target_path": str(target_path), "duration": duration},
                triggered_by="workflow_service"
            )

            return True, f"文件迁移完成 ({duration:.2f}s)"

        except Exception as e:
            error_msg = f"迁移文件异常: {str(e)}"
            logger.exception(error_msg)

            submission.status = SubmissionStatus.FAILED
            submission.error_message = error_msg
            submission.step_details["migrating"] = {"status": "failed", "error": error_msg}
            await submission.save()

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.MIGRATE_FAILED,
                message=error_msg,
                error_message=error_msg,
                triggered_by="workflow_service"
            )

            return False, error_msg

    def _parse_repo_url(self, url: str) -> Tuple[str, str]:
        """
        解析仓库 URL，提取 author 和 repo

        Examples:
            https://github.com/user/repo -> (user, repo)
            https://gitea.xxx.com/user/repo.git -> (user, repo)
        """
        # 移除 .git 后缀
        url = url.rstrip(".git")

        # 提取最后两个路径段
        parts = url.split("/")
        if len(parts) >= 2:
            author = parts[-2]
            repo = parts[-1]
        else:
            author = "unknown"
            repo = parts[-1] if parts else "unknown"

        # 清理非法字符
        author = re.sub(r'[^a-zA-Z0-9_-]', '-', author)
        repo = re.sub(r'[^a-zA-Z0-9_-]', '-', repo)

        return author, repo


# 单例
workflow_service = WorkflowService()
