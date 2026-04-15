"""
工作流服务 - 执行技能提交的三步工作流

步骤：
1. 克隆仓库 → backend/skills_download/{author}/{repo}/
2. 生成报告 → 执行 skill-report-generator/generate.py
3. 迁移文件 → skills/{author}/{skill-name}/
"""
import asyncio
import io
import os
import re
import shutil
import subprocess
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import httpx

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
    COMPLETED = "completed"


class WorkflowService:
    """工作流服务"""

    # 目录配置
    DOWNLOAD_DIR = Path(__file__).parent.parent.parent / "skills_download"

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
            env=env or dict(os.environ)
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

        # 步骤 1.5: 复制 skill 到 git 目录，并获取目标路径
        success, message, git_target_path = await self._copy_skill_to_git_dir(submission, local_path)
        if not success:
            return False, message

        # 步骤 2: 生成报告（使用 git 目录中的 skill）
        success, message = await self.generate_report(submission, git_target_path)
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
            step: 步骤名称 (cloning/generating)
            local_path: 本地路径（用于 generating）

        Returns:
            (是否成功, 消息)
        """
        if step == WorkflowStep.CLONING:
            return await self.clone_repo(submission)
        elif step == WorkflowStep.GENERATING:
            if not local_path:
                # 优先使用 git_copy 的目标路径（SKILL.md 已在根目录）
                git_copy_info = submission.step_details.get("git_copy", {})
                local_path = git_copy_info.get("target_path") or submission.step_details.get("cloning", {}).get("local_path")
            if not local_path:
                return False, "缺少本地路径信息"
            return await self.generate_report(submission, local_path)
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
            # 优先使用 git_copy 的目标路径（SKILL.md 已在根目录）
            git_copy_info = submission.step_details.get("git_copy", {})
            local_path = git_copy_info.get("target_path") or cloning_info.get("local_path")
            if local_path:
                # 步骤 2: 生成报告
                success, message = await self.generate_report(submission, local_path)
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

            https://github.com/user/repo/blob/main/skills/finalize/SKILL.md
            -> (https://github.com/user/repo.git, main, skills/finalize, True)  # 返回 SKILL.md 所在目录

            https://github.com/user/repo.git (普通URL)
            -> (https://github.com/user/repo.git, None, None)

        Returns:
            (repo_url, branch, folder_path, is_skill_md_path)
            - is_skill_md_path: 是否指向 SKILL.md 文件（需要使用其父目录）
        """
        # 匹配 /tree/<branch>/<path>
        tree_match = re.search(r'github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/tree/([^/]+)/(.+)', url)
        if tree_match:
            owner, repo, branch, folder_path = tree_match.groups()
            repo_url = f"https://github.com/{owner}/{repo}.git"
            return repo_url, branch, folder_path, False

        # 匹配 /blob/<branch>/<path> - 可能指向 SKILL.md
        blob_match = re.search(r'github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/blob/([^/]+)/(.+)', url)
        if blob_match:
            owner, repo, branch, file_path = blob_match.groups()
            repo_url = f"https://github.com/{owner}/{repo}.git"
            # 如果指向 SKILL.md，返回其父目录
            if file_path.endswith("/SKILL.md") or file_path == "SKILL.md":
                skill_dir = str(Path(file_path).parent)
                return repo_url, branch, skill_dir, True
            return repo_url, branch, file_path, False

        return None, None, None, False

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
            parse_result = self._parse_github_web_url(submission.repo_url)
            repo_url, branch, folder_path, is_skill_md_path = parse_result
            if repo_url:
                # GitHub Web URL - 使用稀疏克隆
                logger.info(f"Detected GitHub web URL, folder: {folder_path}, branch: {branch}")

                # 创建目标目录 - 使用 submission_id 避免并发冲突
                local_path = self.DOWNLOAD_DIR / submission.submission_id
                if local_path.exists():
                    shutil.rmtree(local_path, ignore_errors=True)
                local_path.parent.mkdir(parents=True, exist_ok=True)

                # 使用稀疏克隆
                success, message, path = await self._sparse_clone(repo_url, branch, folder_path, local_path, start_time)

                # 稀疏克隆失败时，回退到 GitHub ZIP API（解决 Windows 文件名限制问题）
                if not success:
                    logger.warning(f'{{"event": "sparse_clone_failed", "error": "{message[:200]}"}}')
                    success, message, path = await self._download_github_zip(
                        repo_url, branch, folder_path, local_path, start_time
                    )

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

                # 验证 SKILL.md 是否存在（支持子目录）
                skill_dir = self._find_skill_dir(local_path, folder_path)
                if skill_dir is None:
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

                # 更新 local_path 为 SKILL.md 所在目录
                if skill_dir != local_path:
                    logger.info(f"SKILL.md found in subdirectory: {skill_dir}")
                    local_path = skill_dir

                duration = time.time() - start_time

                # 在 _find_skill_dir 修正路径后保存，确保 step_details 存的是 SKILL.md 所在目录
                submission.step_details["cloning"] = {
                    "status": "completed",
                    "local_path": str(local_path),
                    "author": author,
                    "repo": repo,
                    "folder_path": folder_path,
                    "duration": duration
                }
                await submission.save()

                await SubmissionEvent.create(
                    submission=submission,
                    event_type=SubmissionEventType.CLONE_SUCCESS,
                    message=f"稀疏克隆完成 ({duration:.2f}s)",
                    details={"local_path": str(local_path), "folder_path": folder_path, "duration": duration},
                    triggered_by="workflow_service"
                )

                return True, f"稀疏克隆完成 ({duration:.2f}s)", str(local_path)

            # 普通 URL - 直接克隆
            # 创建目标目录 - 使用 submission_id 避免并发冲突
            local_path = self.DOWNLOAD_DIR / submission.submission_id
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

            # 验证 SKILL.md 是否存在（支持子目录）
            skill_dir = self._find_skill_dir(local_path)
            if skill_dir is None:
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

            # 更新 local_path 为 SKILL.md 所在目录
            if skill_dir != local_path:
                logger.info(f"SKILL.md found in subdirectory: {skill_dir}")
                local_path = skill_dir

            # 在 _find_skill_dir 修正路径后保存，确保 step_details 存的是 SKILL.md 所在目录
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

            # 执行生成器 - 使用异步子进程
            import sys
            env = {
                **os.environ,
                "OPENAI_API_KEY": settings.OPENAI_API_KEY or "",
                "OPENAI_BASE_URL": settings.OPENAI_BASE_URL or "https://api.openai.com/v1",
                "OPENAI_MODEL": settings.OPENAI_MODEL or "gpt-4o",
                "GITEA_SKILLS_BASE_URL": settings.GITEA_SKILLS_BASE_URL,
                # generate.py 的 config.yaml 使用 REPORT_API_* 变量
                "REPORT_API_BASE_URL": settings.REPORT_API_BASE_URL or "",
                "REPORT_API_KEY": settings.REPORT_API_KEY or "",
                "REPORT_API_MODEL": settings.REPORT_API_MODEL or "",
            }
            # 构建生成器命令
            cmd = [sys.executable, str(self.GENERATOR_PATH), "--input", local_path]
            # ZIP 上传不传 source-url，Git 工作流传完整 repo_url
            if submission.source_type != "zip":
                source_url = submission.repo_url or "unknown"
                cmd.extend(["--source-url", source_url])

            returncode, stdout, stderr = await self._run_subprocess(
                cmd,
                timeout=300,
                cwd=str(self.GENERATOR_PATH.parent),
                env=env
            )

            duration = time.time() - start_time

            # 重新获取 submission 对象，避免数据库连接超时
            submission_id = submission.id
            submission = await Submission.get(id=submission_id)

            if returncode != 0:
                error_detail = (stderr + stdout)[:500] if stdout else stderr[:500]
                error_msg = f"生成报告失败: {error_detail}"
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
                error_detail = (stdout or "")[:300]
                error_msg = f"报告文件未生成: skill-report.json, generate.py 输出: {error_detail}"
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

            # 查找 SKILL.md 所在目录（支持子目录）
            skill_dir = self._find_skill_dir(local_path)
            if skill_dir is None:
                error_msg = "ZIP 内未找到 SKILL.md 文件。请确保 ZIP 压缩包包含 SKILL.md 文件"
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

            # 更新 local_path 为 SKILL.md 所在目录
            if skill_dir != local_path:
                logger.info(f"SKILL.md found in subdirectory: {skill_dir}")
                local_path = skill_dir

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

    async def _download_github_zip(
        self,
        repo_url: str,
        branch: str,
        folder_path: str,
        local_path: Path,
        start_time: float
    ) -> Tuple[bool, str, Optional[str]]:
        """
        通过 GitHub ZIP API 下载指定文件夹（Windows 兼容回退方案）

        当 sparse clone 因 Windows 文件名限制（如冒号）失败时使用此方法。
        通过 HTTP API 下载整个仓库的 ZIP 包，只解压目标文件夹。
        """
        # 从 repo_url 提取 owner/repo（格式: https://github.com/{owner}/{repo}.git）
        match = re.search(r'github\.com/([^/]+)/([^/]+?)(?:\.git)?$', repo_url)
        if not match:
            return False, f"无法从 repo_url 解析 owner/repo: {repo_url}", None

        owner, repo_name = match.groups()
        zip_url = f"https://api.github.com/repos/{owner}/{repo_name}/zipball/{branch or 'main'}"

        logger.info(f'{{"event": "github_zip_fallback", "url": "{zip_url}", "folder": "{folder_path}"}}')

        try:
            # 清理 sparse clone 可能残留的 .git 目录
            if local_path.exists():
                shutil.rmtree(local_path, ignore_errors=True)
            local_path.mkdir(parents=True, exist_ok=True)

            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                response = await client.get(
                    zip_url,
                    headers={"User-Agent": "skills4sec-workflow/1.0"}
                )

            if response.status_code != 200:
                return False, f"GitHub ZIP 下载失败: HTTP {response.status_code}", None

            # GitHub ZIP 根目录格式为 {owner}-{repo}-{hash}/
            zip_bytes = io.BytesIO(response.content)
            with zipfile.ZipFile(zip_bytes) as zf:
                namelist = zf.namelist()
                if not namelist:
                    return False, "ZIP 文件为空", None

                # 确定 GitHub 自动生成的前缀（第一个 / 之前的部分）
                prefix = namelist[0].split('/')[0] + '/'

                # 目标路径在 ZIP 中: {prefix}{folder_path}/
                target_prefix = f"{prefix}{folder_path}/"

                extracted_count = 0
                for member in namelist:
                    if not member.startswith(target_prefix) or member.endswith('/'):
                        continue

                    # 相对路径：去掉 target_prefix
                    relative_path = member[len(target_prefix):]
                    if not relative_path:
                        continue

                    target_file = local_path / relative_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    with zf.open(member) as src, open(target_file, 'wb') as dst:
                        dst.write(src.read())
                    extracted_count += 1

                if extracted_count == 0:
                    return False, f"ZIP 中未找到目标文件夹: {folder_path}", None

            duration = time.time() - start_time
            logger.info(f'{{"event": "github_zip_success", "files": {extracted_count}, "duration": {duration:.2f}}}')
            return True, f"GitHub ZIP 下载完成 ({duration:.2f}s)", str(local_path)

        except Exception as e:
            error_msg = f"GitHub ZIP 下载异常: {str(e)}"
            logger.error(f'{{"event": "github_zip_error", "error": "{str(e)}"}}')
            return False, error_msg, None

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

    async def _copy_skill_to_git_dir(
        self,
        submission: Submission,
        local_path: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        将 skill 复制到 skills_download/git/{skill-name}/ 目录

        Args:
            submission: 提交记录
            local_path: 克隆的本地路径

        Returns:
            (是否成功, 消息, 目标路径)
        """
        try:
            local_path = Path(local_path)

            # 查找 SKILL.md 文件
            skill_md = local_path / "SKILL.md"
            if not skill_md.exists():
                return False, "SKILL.md not found", None

            # 解析 skill name
            skill_name = self._parse_skill_name(skill_md)
            if not skill_name:
                return False, "Failed to parse skill name from SKILL.md", None

            # 目标目录: skills_download/git/{skill-name}/
            git_dir = self.DOWNLOAD_DIR / "git"
            target_dir = git_dir / skill_name

            # 创建目标目录
            git_dir.mkdir(parents=True, exist_ok=True)

            # 如果目标目录已存在，先删除
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)

            # 复制整个 skill 目录到目标位置
            shutil.copytree(str(local_path), str(target_dir), dirs_exist_ok=True)

            logger.info(f"Copied skill to {target_dir}")

            # 更新 submission 的 step_details
            submission.step_details["git_copy"] = {
                "status": "completed",
                "skill_name": skill_name,
                "target_path": str(target_dir)
            }
            await submission.save()

            return True, f"Skill copied to {target_dir}", str(target_dir)

        except Exception as e:
            error_msg = f"Failed to copy skill to git dir: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, None

    def _parse_skill_name(self, skill_md_path: Path) -> Optional[str]:
        """
        从 SKILL.md 解析 skill name

        Args:
            skill_md_path: SKILL.md 文件路径

        Returns:
            skill name，如果解析失败返回 None
        """
        try:
            content = skill_md_path.read_text(encoding="utf-8")
            # 解析 YAML front matter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 2:
                    import yaml
                    metadata = yaml.safe_load(parts[1])
                    if metadata and "name" in metadata:
                        return metadata["name"]
        except Exception as e:
            logger.warning(f"Failed to parse skill name from {skill_md_path}: {e}")
        return None

    def _find_skill_dir(self, local_path: Path, folder_path: Optional[str] = None) -> Optional[Path]:
        """
        查找包含 SKILL.md 的目录

        查找顺序：
        1. local_path / folder_path / SKILL.md (稀疏克隆的子目录)
        2. local_path / SKILL.md (根目录)
        3. 递归搜索 local_path 下的所有 SKILL.md

        Args:
            local_path: 克隆的本地目录
            folder_path: 稀疏克隆的子目录路径（如果有）

        Returns:
            SKILL.md 所在的目录，如果未找到返回 None
        """
        # 1. 检查稀疏克隆的子目录
        if folder_path:
            skill_in_subdir = local_path / folder_path / "SKILL.md"
            if skill_in_subdir.exists():
                return local_path / folder_path

        # 2. 检查根目录
        skill_in_root = local_path / "SKILL.md"
        if skill_in_root.exists():
            return local_path

        # 3. 递归搜索（支持仓库内有多个 skills 子目录的情况）
        skill_files = list(local_path.rglob("SKILL.md"))
        # 排除 .git 目录
        skill_files = [f for f in skill_files if ".git" not in str(f)]

        if len(skill_files) == 1:
            # 只有一个 SKILL.md，返回其父目录
            return skill_files[0].parent
        elif len(skill_files) > 1:
            # 多个 SKILL.md，选择最短路径的（最接近根目录的）
            skill_files.sort(key=lambda f: len(str(f.relative_to(local_path))))
            logger.info(f"Found {len(skill_files)} SKILL.md files, using: {skill_files[0]}")
            return skill_files[0].parent

        return None


# 单例
workflow_service = WorkflowService()
