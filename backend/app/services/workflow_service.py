"""
工作流服务 - 执行技能提交的三步工作流

步骤：
1. 克隆仓库 → backend/skills_download/{author}/{repo}/
2. 生成报告 → 执行 skill-report-generator/generate.py
3. 迁移文件 → skills/{author}/{skill-name}/
"""
import asyncio
import os
import re
import shutil
import subprocess
import time
import zipfile
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

    async def _run_subprocess(
        self,
        cmd: list,
        timeout: int = 120,
        cwd: Optional[str] = None,
        env: Optional[dict] = None
    ) -> Tuple[int, str, str]:
        """
        异步执行子进程，不阻塞事件循环

        Args:
            cmd: 命令和参数列表
            timeout: 超时秒数
            cwd: 工作目录
            env: 环境变量

        Returns:
            (returncode, stdout, stderr)
        """
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env or os.environ
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            return (
                process.returncode or 0,
                stdout.decode('utf-8', errors='replace'),
                stderr.decode('utf-8', errors='replace')
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise

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
        step1_name = "解压文件" if submission.source_type == "zip" else "克隆仓库"
        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.CLONE_STARTED,
            new_status=SubmissionStatus.CLONING,
            message=f"工作流已启动，开始{step1_name}",
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

    async def continue_workflow(self, submission: Submission) -> Tuple[bool, str]:
        """
        从当前步骤继续执行工作流（克隆完成后自动继续生成和迁移）

        Args:
            submission: 提交记录

        Returns:
            (是否成功, 消息)
        """
        current_status = submission.status
        logger.info(f"Continuing workflow for {submission.submission_id}, current status: {current_status}")

        # 如果克隆完成，自动继续生成
        cloning_info = submission.step_details.get("cloning", {})
        if cloning_info.get("status") == "completed":
            local_path = cloning_info.get("local_path")
            if local_path:
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

                return True, "工作流完成"

        return False, f"无法确定下一步，当前状态: {current_status}"

    def _parse_github_web_url(self, url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        解析 GitHub 网页 URL，提取仓库地址、分支和文件夹路径

        Examples:
            https://github.com/user/repo/tree/main/skills/.curated/aspnet-core
            -> (https://github.com/user/repo.git, main, skills/.curated/aspnet-core)

            https://github.com/user/repo/blob/main/README.md
            -> (https://github.com/user/repo.git, main, README.md)

            https://github.com/user/repo.git (普通URL)
            -> (https://github.com/user/repo.git, None, None)
        """
        # 匹配 /tree/<branch>/<path> 或 /blob/<branch>/<path>
        tree_match = re.search(r'github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/tree/([^/]+)/(.+)', url)
        if tree_match:
            owner, repo, branch, folder_path = tree_match.groups()
            repo_url = f"https://github.com/{owner}/{repo}.git"
            return repo_url, branch, folder_path

        # 匹配 /blob/<branch>/<path>
        blob_match = re.search(r'github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/blob/([^/]+)/(.+)', url)
        if blob_match:
            owner, repo, branch, file_path = blob_match.groups()
            repo_url = f"https://github.com/{owner}/{repo}.git"
            return repo_url, branch, file_path

        return None, None, None

    async def clone_repo(self, submission: Submission) -> Tuple[bool, str, Optional[str]]:
        """
        克隆仓库（支持单个文件夹的稀疏克隆）

        Returns:
            (是否成功, 消息, 本地路径)
        """
        start_time = time.time()
        logger.info(f"Processing submission: {submission.submission_id}, source_type: {submission.source_type}")

        # 更新状态
        submission.status = SubmissionStatus.CLONING
        submission.current_step = WorkflowStep.CLONING
        await submission.save()

        await SubmissionEvent.create(
            submission=submission,
            event_type=SubmissionEventType.CLONE_STARTED,
            message=f"开始处理: source_type={submission.source_type}",
            triggered_by="workflow_service"
        )

        # ========== ZIP 处理分支 ==========
        if submission.source_type == "zip":
            return await self._extract_zip(submission, start_time)

        # ========== Git 处理分支 ==========
        try:
            # 解析 author 和 repo
            author, repo = self._parse_repo_url(submission.repo_url)

            # 检查是否是 GitHub Web URL
            repo_url, branch, folder_path = self._parse_github_web_url(submission.repo_url)
            if repo_url:
                # GitHub Web URL - 使用稀疏克隆
                logger.info(f"Detected GitHub web URL, folder: {folder_path}, branch: {branch}")

                # 创建目标目录
                local_path = self.DOWNLOAD_DIR / author / repo
                if local_path.exists():
                    shutil.rmtree(local_path, ignore_errors=True)
                local_path.parent.mkdir(parents=True, exist_ok=True)

                # 使用稀疏克隆
                success, message, path = self._sparse_clone(repo_url, branch, folder_path, local_path, start_time)
                if not success:
                    # 设置失败状态
                    submission.status = SubmissionStatus.FAILED
                    submission.error_message = message
                    submission.step_details["cloning"] = {
                        "status": "failed",
                        "error": message,
                        "duration": time.time() - start_time
                    }
                    await submission.save()

                    await SubmissionEvent.create(
                        submission=submission,
                        event_type=SubmissionEventType.CLONE_FAILED,
                        message=message,
                        error_message=message,
                        triggered_by="workflow_service"
                    )
                    return False, message, None

                # 更新 submission 的 repo_url 为真实仓库地址
                submission.repo_url = repo_url
                submission.step_details["cloning"] = {
                    "status": "completed",
                    "local_path": str(local_path),
                    "author": author,
                    "repo": repo,
                    "folder_path": folder_path,
                    "duration": time.time() - start_time
                }
                await submission.save()

                await SubmissionEvent.create(
                    submission=submission,
                    event_type=SubmissionEventType.CLONE_SUCCESS,
                    message=f"稀疏克隆完成 ({time.time() - start_time:.2f}s)",
                    details={"local_path": str(local_path), "folder_path": folder_path, "duration": time.time() - start_time},
                    triggered_by="workflow_service"
                )

                # 验证 SKILL.md 是否存在
                if not (local_path / "SKILL.md").exists():
                    error_msg = "仓库中未找到 SKILL.md 文件，不支持的技能格式"
                    submission.status = SubmissionStatus.FAILED
                    submission.error_message = error_msg
                    submission.step_details["cloning"] = {
                        "status": "failed",
                        "error": error_msg,
                        "duration": time.time() - start_time
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

                duration = time.time() - start_time
                return True, f"稀疏克隆完成 ({duration:.2f}s)", str(local_path)

            # 普通 URL - 直接克隆
            # 创建目标目录
            local_path = self.DOWNLOAD_DIR / author / repo
            if local_path.exists():
                shutil.rmtree(local_path, ignore_errors=True)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # 执行 git clone（异步）
            returncode, stdout, stderr = await self._run_subprocess(
                ["git", "clone", "--depth", "1", submission.repo_url, str(local_path)],
                timeout=120
            )

            duration = time.time() - start_time

            if returncode != 0:
                error_msg = f"克隆失败: {stderr[:500]}"
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

            # 验证 SKILL.md 是否存在
            if not (local_path / "SKILL.md").exists():
                error_msg = "仓库中未找到 SKILL.md 文件，不支持的技能格式"
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

            # 执行生成器 - 使用异步子进程
            import sys
            env = {
                **os.environ,
                "OPENAI_API_KEY": settings.OPENAI_API_KEY or "",
                "OPENAI_BASE_URL": settings.OPENAI_BASE_URL or "https://api.openai.com/v1",
                "OPENAI_MODEL": settings.OPENAI_MODEL or "gpt-4o",
                "GITEA_SKILLS_BASE_URL": settings.GITEA_SKILLS_BASE_URL,
            }
            # 设置 source_url：Git 用仓库地址，ZIP 用 Gitea 技能库地址
            if submission.source_type == "zip":
                source_url = f"{settings.GITEA_SKILLS_BASE_URL}/{submission.name}"
            else:
                source_url = submission.repo_url or "unknown"

            returncode, stdout, stderr = await self._run_subprocess(
                [sys.executable, str(self.GENERATOR_PATH), "--input", local_path, "--source-url", source_url],
                timeout=300,
                cwd=str(self.GENERATOR_PATH.parent),
                env=env
            )

            duration = time.time() - start_time

            # 重新获取 submission 对象，避免数据库连接超时
            submission_id = submission.id
            submission = await Submission.get(id=submission_id)

            if returncode != 0:
                error_msg = f"生成报告失败: {stderr[:500]}"
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
                    submission_id=submission_id,
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

            # 重新获取 submission 对象
            sub = await Submission.get_or_none(id=submission.id)
            if sub:
                sub.status = SubmissionStatus.FAILED
                sub.error_message = error_msg
                sub.step_details["generating"] = {"status": "failed", "error": error_msg}
                await sub.save()

                await SubmissionEvent.create(
                    submission_id=sub.id,
                    event_type=SubmissionEventType.GENERATE_FAILED,
                    message=error_msg,
                    error_message=error_msg,
                    triggered_by="workflow_service"
                )

            return False, error_msg

        except Exception as e:
            error_msg = f"生成报告异常: {str(e)}"
            logger.exception(error_msg)

            # 重新获取 submission 对象
            sub = await Submission.get_or_none(id=submission.id)
            if sub:
                sub.status = SubmissionStatus.FAILED
                sub.error_message = error_msg
                sub.step_details["generating"] = {"status": "failed", "error": error_msg}
                await sub.save()

                await SubmissionEvent.create(
                    submission_id=sub.id,
                    event_type=SubmissionEventType.GENERATE_FAILED,
                    message=error_msg,
                    error_message=error_msg,
                    triggered_by="workflow_service"
                )

            return False, error_msg
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

    async def _extract_zip(
        self,
        submission: Submission,
        start_time: float
    ) -> Tuple[bool, str, Optional[str]]:
        """
        解压 ZIP 文件到本地目录

        Args:
            submission: 提交记录
            start_time: 开始时间

        Returns:
            (是否成功, 消息, 本地路径)
        """
        zip_path = submission.zip_path
        if not zip_path:
            error_msg = "ZIP 路径不存在"
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

        zip_path = Path(zip_path)
        if not zip_path.exists():
            error_msg = f"ZIP 文件不存在: {zip_path}"
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

        try:
            # 创建目标目录 - 使用技能名称而非 UUID
            # 清理名称中的特殊字符
            safe_name = "".join(c for c in submission.name if c.isalnum() or c in ('-', '_')).rstrip()
            if not safe_name:
                safe_name = submission.submission_id[:8]
            local_path = self.DOWNLOAD_DIR / "zip" / safe_name
            if local_path.exists():
                shutil.rmtree(local_path, ignore_errors=True)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # 解压 ZIP
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(local_path)

            # 检查 SKILL.md 是否直接存在于解压目录中（不允许中间有文件夹）
            skill_md = local_path / "SKILL.md"
            if not skill_md.exists():
                error_msg = "ZIP 内未找到 SKILL.md 文件。请确保 ZIP 压缩包直接包含 SKILL.md（不要有额外的文件夹包裹）"
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

            duration = time.time() - start_time
            logger.info(f"ZIP extracted in {duration:.2f}s")

            # 更新 submission
            submission.step_details["cloning"] = {
                "status": "completed",
                "local_path": str(local_path),
                "source": "zip",
                "duration": duration
            }
            await submission.save()

            await SubmissionEvent.create(
                submission=submission,
                event_type=SubmissionEventType.CLONE_SUCCESS,
                message=f"ZIP 解压完成 ({duration:.2f}s)",
                details={"local_path": str(local_path), "duration": duration},
                triggered_by="workflow_service"
            )

            return True, f"ZIP 解压完成 ({duration:.2f}s)", str(local_path)

        except zipfile.BadZipFile:
            error_msg = "无效的 ZIP 文件"
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
            error_msg = f"ZIP 解压异常: {str(e)}"
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

    async def _sparse_clone(
        self,
        repo_url: str,
        branch: str,
        folder_path: str,
        local_path: Path,
        start_time: float
    ) -> Tuple[bool, str, Optional[str]]:
        """
        使用 git sparse-checkout 克隆单个文件夹（异步版本）

        Args:
            repo_url: 仓库 URL
            branch: 分支名
            folder_path: 文件夹路径
            local_path: 本地目标路径
            start_time: 开始时间

        Returns:
            (是否成功, 消息, 本地路径)
        """
        try:
            # Step 1: 初始化空仓库（异步）
            returncode, stdout, stderr = await self._run_subprocess(
                ["git", "init", str(local_path)],
                timeout=30,
                cwd=str(local_path.parent)
            )
            if returncode != 0:
                return False, f"git init 失败: {stderr[:200]}", None

            # Step 2: 添加远程仓库（异步）
            returncode, stdout, stderr = await self._run_subprocess(
                ["git", "remote", "add", "origin", repo_url],
                timeout=30,
                cwd=str(local_path)
            )
            if returncode != 0:
                return False, f"git remote add 失败: {stderr[:200]}", None

            # Step 3: 启用 sparse-checkout（异步）
            returncode, stdout, stderr = await self._run_subprocess(
                ["git", "config", "core.sparseCheckout", "true"],
                timeout=30,
                cwd=str(local_path)
            )
            if returncode != 0:
                return False, f"git sparse-checkout 启用失败: {stderr[:200]}", None

            # Step 4: 配置稀疏检出的文件夹
            with open(local_path / ".git" / "info" / "sparse-checkout", "w") as f:
                f.write(f"/{folder_path}\n")

            # Step 5: 拉取指定分支（异步）
            returncode, stdout, stderr = await self._run_subprocess(
                ["git", "pull", "--depth=1", "origin", branch or "main"],
                timeout=180,
                cwd=str(local_path)
            )
            if returncode != 0:
                # 尝试默认分支
                returncode, stdout, stderr = await self._run_subprocess(
                    ["git", "pull", "--depth=1", "origin", "main"],
                    timeout=180,
                    cwd=str(local_path)
                )
                if returncode != 0:
                    error_msg = f"git pull 失败: {stderr[:500]}"
                    logger.error(error_msg)
                    return False, error_msg, None

            duration = time.time() - start_time
            logger.info(f"Sparse clone completed in {duration:.2f}s")

            # 解析 author 和 repo
            author, repo = self._parse_repo_url(repo_url)

            submission = None  # 将在调用处更新
            return True, f"稀疏克隆完成 ({duration:.2f}s)", str(local_path)

        except subprocess.TimeoutExpired:
            return False, "克隆超时（超过180秒）", None
        except Exception as e:
            return False, f"稀疏克隆异常: {str(e)}", None

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
