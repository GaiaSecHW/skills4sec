# 极简工作流实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 简化技能提交流程，从 Git URL 直接到技能入库，移除 Issue/PR/审批流程

**Architecture:** 三步工作流（克隆→生成报告→迁移），使用 WorkflowService 执行，状态存储在 Submission.step_details

**Tech Stack:** FastAPI + Tortoise-ORM + APScheduler + httpx

---

## 文件结构

### 需要修改的文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/app/models/submission.py` | 修改 | 简化状态枚举，添加 current_step/step_details 字段 |
| `backend/app/api/admin/submissions.py` | 修改 | 简化 API，添加 start/retry-step 接口 |
| `backend/app/tasks/submission_tasks.py` | 修改 | 移除不需要的定时任务 |
| `backend/app/tasks/scheduler.py` | 修改 | 移除不需要的任务注册 |
| `backend/app/services/__init__.py` | 修改 | 导出 WorkflowService |
| `backend/static/admin/index.html` | 修改 | 更新前端 UI |

### 需要创建的文件

| 文件 | 说明 |
|------|------|
| `backend/app/services/workflow_service.py` | 核心工作流服务 |

### 需要删除的文件

| 文件 | 原因 |
|------|------|
| `backend/app/services/gitea_sync_service.py` | 不再同步 Gitea |
| `backend/app/services/issue_handler.py` | 不再处理 Issue |
| `backend/app/services/retry_service.py` | 不再需要自动重试 |

---

## Chunk 1: 数据模型简化

### Task 1.1: 更新 SubmissionStatus 枚举

**Files:**
- Modify: `backend/app/models/submission.py:11-31`

- [ ] **Step 1: 更新 SubmissionStatus 枚举**

将现有的枚举替换为简化版本：

```python
class SubmissionStatus(str, Enum):
    """提交状态枚举"""
    PENDING = "pending"              # 待处理
    CLONING = "cloning"              # 克隆中
    GENERATING = "generating"        # 生成报告中
    MIGRATING = "migrating"          # 迁移中
    COMPLETED = "completed"          # 已完成
    FAILED = "failed"                # 失败（含失败原因）
```

- [ ] **Step 2: 更新 SubmissionEventType 枚举**

将事件类型替换为简化版本：

```python
class SubmissionEventType(str, Enum):
    """提交事件类型枚举"""
    # 创建
    CREATED = "created"

    # 克隆步骤
    CLONE_STARTED = "clone_started"
    CLONE_SUCCESS = "clone_success"
    CLONE_FAILED = "clone_failed"

    # 生成步骤
    GENERATE_STARTED = "generate_started"
    GENERATE_SUCCESS = "generate_success"
    GENERATE_FAILED = "generate_failed"

    # 迁移步骤
    MIGRATE_STARTED = "migrate_started"
    MIGRATE_SUCCESS = "migrate_success"
    MIGRATE_FAILED = "migrate_failed"

    # 完成
    COMPLETED = "completed"

    # 重试
    RETRY = "retry"
```

- [ ] **Step 3: 添加新字段到 Submission 模型**

在 Submission 类中添加：

```python
    # 工作流步骤
    current_step = fields.CharField(max_length=20, null=True, description="当前步骤")
    step_details = fields.JSONField(default=dict, description="步骤详情")
```

- [ ] **Step 4: 删除不需要的字段**

从 Submission 模型中删除以下字段：

```python
    # 删除 Issue 相关字段
    issue_number = ...
    issue_url = ...
    issue_state = ...
    issue_labels = ...
    issue_created_at = ...

    # 删除 PR 相关字段
    pr_number = ...
    pr_url = ...
    pr_state = ...
    pr_merged = ...

    # 删除审批相关字段
    approved_by = ...
    approved_by_employee_id = ...
    approved_at = ...
    rejected_by = ...
    rejected_by_employee_id = ...
    rejected_at = ...
    reject_reason = ...

    # 删除工作流相关字段
    workflow_run_id = ...
    workflow_run_url = ...
```

- [ ] **Step 5: 更新 is_retryable 和 is_terminal 属性**

```python
    @property
    def is_retryable(self) -> bool:
        """是否可以重试"""
        return self.status == SubmissionStatus.FAILED

    @property
    def is_terminal(self) -> bool:
        """是否已到达终态"""
        return self.status in (
            SubmissionStatus.COMPLETED,
            SubmissionStatus.FAILED,
        )
```

- [ ] **Step 6: 提交模型变更**

```bash
git add backend/app/models/submission.py
git commit -m "refactor(submission): 简化状态枚举，添加工作流步骤字段

- 简化 SubmissionStatus 为 6 个状态
- 简化 SubmissionEventType 为步骤事件
- 添加 current_step 和 step_details 字段
- 移除 Issue/PR/审批相关字段

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 2: 创建 WorkflowService

### Task 2.1: 创建 WorkflowService 核心服务

**Files:**
- Create: `backend/app/services/workflow_service.py`

- [ ] **Step 1: 创建 WorkflowService 文件骨架**

```python
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
```

- [ ] **Step 2: 更新 services/__init__.py 导出**

```python
from app.services.workflow_service import workflow_service, WorkflowService
```

- [ ] **Step 3: 提交 WorkflowService**

```bash
git add backend/app/services/workflow_service.py backend/app/services/__init__.py
git commit -m "feat: 添加 WorkflowService 实现三步工作流

- 克隆仓库到 backend/skills_download/
- 执行 generate.py 生成审计报告
- 迁移文件到 skills/ 目录
- 支持单步重试

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 3: API 简化

### Task 3.1: 简化 submissions API

**Files:**
- Modify: `backend/app/api/admin/submissions.py`

- [ ] **Step 1: 更新导入和 Schema**

移除不需要的导入，更新 Schema：

```python
"""
技能提交管理 API - 极简工作流
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import uuid

from app.models.user import User
from app.models.submission import (
    Submission,
    SubmissionEvent,
    SubmissionStatus,
    SubmissionEventType
)
from app.utils.security import get_current_admin_user, get_current_superuser
from app.services.workflow_service import workflow_service
from app.config import settings

router = APIRouter(prefix="/admin/submissions", tags=["admin-submissions"])


# ============ Schema 定义 ============

class SubmissionCreate(BaseModel):
    """创建提交请求"""
    name: Optional[str] = Field(None, max_length=200, description="技能名称（可选，从仓库解析）")
    repo_url: str = Field(..., max_length=500, description="Git 仓库地址")
    description: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=50)
    contact: Optional[str] = Field(None, max_length=200)


class SubmissionOut(BaseModel):
    """提交输出"""
    id: int
    submission_id: str
    name: str
    repo_url: str
    description: Optional[str]
    category: Optional[str]
    contact: Optional[str]
    submitter_employee_id: Optional[str]
    status: str
    current_step: Optional[str]
    step_details: dict
    skill_count: int
    processed_skills: int
    failed_skills: int
    highest_risk: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    processing_started_at: Optional[datetime]
    processing_completed_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class SubmissionEventOut(BaseModel):
    """提交事件输出"""
    id: int
    submission_id: int
    event_type: str
    old_status: Optional[str]
    new_status: Optional[str]
    message: Optional[str]
    details: Optional[dict]
    triggered_by: Optional[str]
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class StartWorkflowRequest(BaseModel):
    """启动工作流请求"""
    pass


class RetryStepRequest(BaseModel):
    """重试步骤请求"""
    step: str = Field(..., description="步骤名称: cloning/generating/migrating")
```

- [ ] **Step 2: 更新辅助函数**

```python
def submission_to_out(sub: Submission) -> dict:
    """转换为输出格式"""
    return {
        "id": sub.id,
        "submission_id": sub.submission_id,
        "name": sub.name,
        "repo_url": sub.repo_url,
        "description": sub.description,
        "category": sub.category,
        "contact": sub.contact,
        "submitter_employee_id": sub.submitter_employee_id,
        "status": sub.status.value if isinstance(sub.status, SubmissionStatus) else sub.status,
        "current_step": sub.current_step,
        "step_details": sub.step_details or {},
        "skill_count": sub.skill_count,
        "processed_skills": sub.processed_skills,
        "failed_skills": sub.failed_skills,
        "highest_risk": sub.highest_risk,
        "error_message": sub.error_message,
        "created_at": sub.created_at,
        "updated_at": sub.updated_at,
        "processing_started_at": sub.processing_started_at,
        "processing_completed_at": sub.processing_completed_at,
        "completed_at": sub.completed_at,
    }


def event_to_out(event: SubmissionEvent) -> dict:
    """转换事件为输出格式"""
    return {
        "id": event.id,
        "submission_id": event.submission_id,
        "event_type": event.event_type.value if isinstance(event.event_type, SubmissionEventType) else event.event_type,
        "old_status": event.old_status.value if event.old_status and isinstance(event.old_status, SubmissionStatus) else event.old_status,
        "new_status": event.new_status.value if event.new_status and isinstance(event.new_status, SubmissionStatus) else event.new_status,
        "message": event.message,
        "details": event.details,
        "triggered_by": event.triggered_by,
        "error_message": event.error_message,
        "created_at": event.created_at,
    }
```

- [ ] **Step 3: 更新 API 路由**

保留并简化以下路由：

```python
# ============ API 接口 ============

@router.get("", response_model=dict)
async def list_submissions(
    request: Request,
    skip: int = Query(0, ge=0, description="偏移量"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    admin: User = Depends(get_current_admin_user)
):
    """获取提交列表 (管理员)"""
    query = Submission.all()

    if status:
        try:
            status_enum = SubmissionStatus(status)
            query = query.filter(status=status_enum)
        except ValueError:
            pass

    if keyword:
        query = query.filter(name__icontains=keyword) | Submission.filter(repo_url__icontains=keyword)

    total = await query.count()
    submissions = await query.offset(skip).limit(limit).order_by("-created_at")

    return {
        "success": True,
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [submission_to_out(s) for s in submissions]
    }


@router.get("/stats", response_model=dict)
async def get_submission_stats(
    admin: User = Depends(get_current_admin_user)
):
    """获取提交统计"""
    from datetime import date

    total = await Submission.all().count()

    by_status = {}
    for s in SubmissionStatus:
        count = await Submission.filter(status=s).count()
        by_status[s.value] = count

    today_start = datetime.combine(date.today(), datetime.min.time())
    today_count = await Submission.filter(created_at__gte=today_start).count()

    return {
        "success": True,
        "data": {
            "total": total,
            "pending": by_status.get("pending", 0),
            "processing": by_status.get("cloning", 0) + by_status.get("generating", 0) + by_status.get("migrating", 0),
            "completed": by_status.get("completed", 0),
            "failed": by_status.get("failed", 0),
            "by_status": by_status,
            "today_count": today_count
        }
    }


@router.post("", response_model=dict)
async def create_submission(
    request: Request,
    data: SubmissionCreate,
    admin: User = Depends(get_current_admin_user)
):
    """创建提交"""
    # 生成提交 ID
    submission_id = str(uuid.uuid4())

    # 从 URL 解析名称
    name = data.name
    if not name:
        parts = data.repo_url.rstrip(".git").split("/")
        name = parts[-1] if parts else "unknown"

    # 创建记录
    submission = await Submission.create(
        submission_id=submission_id,
        name=name,
        repo_url=data.repo_url,
        description=data.description,
        category=data.category,
        contact=data.contact,
        submitter_id=admin.id,
        submitter_employee_id=admin.employee_id,
        status=SubmissionStatus.PENDING,
        step_details={}
    )

    # 记录事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.CREATED,
        new_status=SubmissionStatus.PENDING,
        message=f"创建提交: {name}",
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    return {
        "success": True,
        "message": "提交已创建",
        "data": submission_to_out(submission)
    }


@router.get("/{submission_id}", response_model=dict)
async def get_submission_detail(
    submission_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """获取提交详情（含事件日志）"""
    submission = await Submission.get_or_none(id=submission_id).prefetch_related("events")
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    events = await submission.events.all().order_by("created_at")

    return {
        "success": True,
        "data": {
            "submission": submission_to_out(submission),
            "events": [event_to_out(e) for e in events]
        }
    }


@router.post("/{submission_id}/start", response_model=dict)
async def start_workflow(
    request: Request,
    submission_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """开始处理提交"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    if submission.status != SubmissionStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前状态 {submission.status} 不支持启动"
        )

    # 在后台启动工作流
    import asyncio
    asyncio.create_task(workflow_service.start_workflow(submission))

    return {
        "success": True,
        "message": "工作流已启动",
        "data": submission_to_out(submission)
    }


@router.post("/{submission_id}/retry-step", response_model=dict)
async def retry_step(
    request: Request,
    submission_id: int,
    data: RetryStepRequest,
    admin: User = Depends(get_current_admin_user)
):
    """重试单个步骤"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    if submission.status != SubmissionStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有失败状态才能重试"
        )

    valid_steps = ["cloning", "generating", "migrating"]
    if data.step not in valid_steps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效步骤，可选: {valid_steps}"
        )

    # 记录重试事件
    await SubmissionEvent.create(
        submission=submission,
        event_type=SubmissionEventType.RETRY,
        message=f"管理员 {admin.employee_id} 重试步骤: {data.step}",
        details={"step": data.step},
        actor_id=admin.id,
        actor_employee_id=admin.employee_id,
        triggered_by="admin"
    )

    # 在后台执行步骤
    import asyncio
    asyncio.create_task(workflow_service.execute_step(submission, data.step))

    return {
        "success": True,
        "message": f"步骤 {data.step} 重试中",
        "data": submission_to_out(submission)
    }


@router.delete("/{submission_id}", response_model=dict)
async def delete_submission(
    request: Request,
    submission_id: int,
    admin: User = Depends(get_current_admin_user)
):
    """删除提交"""
    submission = await Submission.get_or_none(id=submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="提交不存在")

    # 删除相关事件
    await SubmissionEvent.filter(submission=submission).delete()

    # 删除提交
    await submission.delete()

    return {
        "success": True,
        "message": "提交已删除"
    }
```

- [ ] **Step 4: 提交 API 变更**

```bash
git add backend/app/api/admin/submissions.py
git commit -m "refactor(api): 简化 submissions API

- 移除 Issue/PR/审批相关接口
- 添加 start/retry-step 接口
- 简化 Schema 输出

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 4: 清理不需要的服务和任务

### Task 4.1: 删除不需要的服务文件

**Files:**
- Delete: `backend/app/services/gitea_sync_service.py`
- Delete: `backend/app/services/issue_handler.py`
- Delete: `backend/app/services/retry_service.py`

- [ ] **Step 1: 删除服务文件**

```bash
rm backend/app/services/gitea_sync_service.py
rm backend/app/services/issue_handler.py
rm backend/app/services/retry_service.py
```

- [ ] **Step 2: 更新 services/__init__.py**

移除已删除服务的导入。

- [ ] **Step 3: 提交删除**

```bash
git add -A
git commit -m "refactor: 删除不需要的服务

- 删除 gitea_sync_service.py
- 删除 issue_handler.py
- 删除 retry_service.py

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 4.2: 简化定时任务

**Files:**
- Modify: `backend/app/tasks/submission_tasks.py`
- Modify: `backend/app/tasks/scheduler.py`

- [ ] **Step 1: 简化 submission_tasks.py**

只保留清理任务：

```python
"""
提交相关定时任务 - 清理和统计
"""
from datetime import datetime, timedelta

from app.models.submission import Submission, SubmissionEvent, SubmissionStatus
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

    每天调用一次，标记超过1天未更新的 processing 状态为 failed
    """
    stale_threshold = datetime.utcnow() - timedelta(days=1)

    stale_submissions = await Submission.filter(
        status__in=[
            SubmissionStatus.CLONING,
            SubmissionStatus.GENERATING,
            SubmissionStatus.MIGRATING
        ],
        updated_at__lt=stale_threshold
    ).all()

    updated_count = 0
    for submission in stale_submissions:
        submission.status = SubmissionStatus.FAILED
        submission.error_message = "处理超时（超过1天未更新）"
        await submission.save()
        updated_count += 1

    if updated_count > 0:
        logger.info(f"Marked {updated_count} stale submissions as failed")

    return {"updated": updated_count}


async def generate_daily_stats():
    """
    生成每日统计

    每天凌晨调用
    """
    from datetime import date

    yesterday = date.today() - timedelta(days=1)
    yesterday_start = datetime.combine(yesterday, datetime.min.time())
    yesterday_end = datetime.combine(yesterday, datetime.max.time())

    total = await Submission.filter(
        created_at__gte=yesterday_start,
        created_at__lte=yesterday_end
    ).count()

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
```

- [ ] **Step 2: 简化 scheduler.py**

```python
"""
任务调度器 - APScheduler 集成
"""
from typing import Callable, Dict, Any
from datetime import datetime

from app.core import get_logger

logger = get_logger("scheduler")

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
                max_instances=1,
                coalesce=True,
            )
            logger.info(
                "Registered task",
                event="task_registered",
                task_name=task_func.__name__,
                interval_seconds=interval_seconds,
            )

        logger.info("Scheduler setup completed", event="scheduler_setup_completed")
        return scheduler

    except ImportError:
        logger.warning(
            "APScheduler not installed, scheduled tasks disabled",
            event="apscheduler_not_installed",
        )
        return None


def start_scheduler():
    """启动调度器"""
    global scheduler

    if scheduler:
        scheduler.start()
        logger.info("Scheduler started", event="scheduler_started")
    else:
        logger.warning("Scheduler not available", event="scheduler_not_available")


def shutdown_scheduler():
    """关闭调度器"""
    global scheduler

    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown", event="scheduler_shutdown")


async def run_task_manually(task_name: str) -> Dict[str, Any]:
    """手动触发任务"""
    from app.tasks.submission_tasks import (
        cleanup_old_events,
        cleanup_stale_submissions,
        generate_daily_stats,
    )

    tasks = {
        "cleanup_old_events": cleanup_old_events,
        "cleanup_stale_submissions": cleanup_stale_submissions,
        "generate_daily_stats": generate_daily_stats,
    }

    if task_name not in tasks:
        return {"success": False, "error": f"Unknown task: {task_name}"}

    task_func = tasks[task_name]

    try:
        logger.info(
            "Manually running task",
            event="task_manual_run",
            task_name=task_name,
        )
        result = await task_func()
        return {
            "success": True,
            "task": task_name,
            "executed_at": datetime.utcnow().isoformat(),
            "result": result
        }
    except Exception as e:
        logger.exception(
            "Task failed",
            event="task_failed",
            task_name=task_name,
            error=e,
        )
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
```

- [ ] **Step 3: 提交任务变更**

```bash
git add backend/app/tasks/submission_tasks.py backend/app/tasks/scheduler.py
git commit -m "refactor(tasks): 简化定时任务

- 移除 sync_gitea_status、process_pending_retries 等任务
- 只保留 cleanup_old_events、cleanup_stale_submissions、generate_daily_stats

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 5: 前端更新

### Task 5.1: 更新管理后台 UI

**Files:**
- Modify: `backend/static/admin/index.html`

- [ ] **Step 1: 更新提交列表页面**

修改提交列表的显示，添加进度条：

```html
<!-- 在 submissions 列表渲染部分更新 -->
<script>
// 更新 renderSubmissions 函数
function renderSubmissions(submissions) {
    const tbody = document.getElementById('submissions-tbody');
    tbody.innerHTML = submissions.map(sub => {
        const progress = calculateProgress(sub);
        const statusBadge = getStatusBadge(sub.status);

        return `
            <tr>
                <td>${sub.name}</td>
                <td><a href="${sub.repo_url}" target="_blank">${truncateUrl(sub.repo_url)}</a></td>
                <td>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${progress}%"></div>
                        <span class="progress-text">${progress}%</span>
                    </div>
                </td>
                <td>${statusBadge}</td>
                <td>
                    <button class="btn-sm btn-primary" onclick="showDetail(${sub.id})">详情</button>
                    ${sub.status === 'pending' ? `<button class="btn-sm btn-success" onclick="startWorkflow(${sub.id})">开始</button>` : ''}
                    ${sub.status === 'failed' ? `<button class="btn-sm btn-warning" onclick="showRetryModal(${sub.id})">重试</button>` : ''}
                    <button class="btn-sm btn-danger" onclick="deleteSubmission(${sub.id})">删除</button>
                </td>
            </tr>
        `;
    }).join('');
}

function calculateProgress(sub) {
    const steps = ['cloning', 'generating', 'migrating'];
    const currentStep = sub.current_step;

    if (sub.status === 'completed') return 100;
    if (sub.status === 'pending') return 0;
    if (sub.status === 'failed') {
        const stepIndex = steps.indexOf(currentStep);
        return stepIndex >= 0 ? (stepIndex + 1) * 25 : 0;
    }

    const stepIndex = steps.indexOf(currentStep);
    return stepIndex >= 0 ? (stepIndex + 1) * 25 : 25;
}

function getStatusBadge(status) {
    const badges = {
        'pending': '<span class="badge badge-secondary">待处理</span>',
        'cloning': '<span class="badge badge-info">克隆中</span>',
        'generating': '<span class="badge badge-info">生成中</span>',
        'migrating': '<span class="badge badge-info">迁移中</span>',
        'completed': '<span class="badge badge-success">已完成</span>',
        'failed': '<span class="badge badge-danger">失败</span>'
    };
    return badges[status] || `<span class="badge">${status}</span>`;
}

async function startWorkflow(id) {
    const res = await api(`/admin/submissions/${id}/start`, { method: 'POST' });
    if (res && res.success) {
        showToast('工作流已启动', 'success');
        loadSubmissions();
    } else {
        showError(res, '启动失败');
    }
}

async function showRetryModal(id) {
    const sub = await api(`/admin/submissions/${id}`);
    if (!sub) return;

    const stepDetails = sub.data.submission.step_details;
    const failedStep = Object.keys(stepDetails).find(k => stepDetails[k].status === 'failed');

    showConfirm(`确定重试步骤 "${failedStep || '未知'}" 吗？`, async () => {
        const res = await api(`/admin/submissions/${id}/retry-step`, {
            method: 'POST',
            body: JSON.stringify({ step: failedStep })
        });
        if (res && res.success) {
            showToast('重试已启动', 'success');
            loadSubmissions();
        } else {
            showError(res, '重试失败');
        }
    });
}
</script>
```

- [ ] **Step 2: 添加进度条 CSS**

```css
/* 进度条样式 */
.progress-bar {
    width: 120px;
    height: 20px;
    background: #e9ecef;
    border-radius: 10px;
    overflow: hidden;
    position: relative;
}

.progress-fill {
    height: 100%;
    background: linear-gradient(135deg, #4a90d9, #3b82f6);
    transition: width 0.3s ease;
}

.progress-text {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 11px;
    font-weight: 600;
    color: #333;
}
```

- [ ] **Step 3: 更新详情弹窗**

```javascript
async function showDetail(id) {
    const res = await api(`/admin/submissions/${id}`);
    if (!res || !res.success) {
        showError(res, '获取详情失败');
        return;
    }

    const sub = res.data.submission;
    const events = res.data.events;

    const steps = ['cloning', 'generating', 'migrating'];
    const stepNames = { cloning: '克隆', generating: '生成报告', migrating: '迁移文件' };

    // 生成步骤进度
    let stepsHtml = '<div class="workflow-steps">';
    steps.forEach((step, i) => {
        const detail = sub.step_details[step] || {};
        const isActive = sub.current_step === step;
        const isCompleted = detail.status === 'completed';
        const isFailed = detail.status === 'failed';

        let stepClass = '';
        if (isCompleted) stepClass = 'completed';
        else if (isActive) stepClass = 'active';
        else if (isFailed) stepClass = 'failed';

        stepsHtml += `
            <div class="workflow-step ${stepClass}">
                <div class="workflow-step-icon">${isCompleted ? '✓' : isFailed ? '!' : i + 1}</div>
                <div class="workflow-step-label">${stepNames[step]}</div>
                ${detail.duration ? `<div class="workflow-step-time">${detail.duration.toFixed(1)}s</div>` : ''}
            </div>
        `;
    });
    stepsHtml += '</div>';

    // 生成事件日志
    let eventsHtml = events.map(e => {
        const time = new Date(e.created_at).toLocaleTimeString();
        return `<div class="event-row">
            <span class="event-time">${time}</span>
            <span class="event-type ${e.event_type.includes('failed') ? 'text-danger' : ''}">${e.message || e.event_type}</span>
        </div>`;
    }).join('');

    document.getElementById('modal-content').innerHTML = `
        <div class="detail-section">
            <h4>基本信息</h4>
            <div class="detail-row"><strong>名称:</strong> ${sub.name}</div>
            <div class="detail-row"><strong>Git URL:</strong> <a href="${sub.repo_url}" target="_blank">${sub.repo_url}</a></div>
            <div class="detail-row"><strong>创建时间:</strong> ${new Date(sub.created_at).toLocaleString()}</div>
        </div>
        <div class="detail-section">
            <h4>工作流进度</h4>
            ${stepsHtml}
        </div>
        <div class="detail-section">
            <h4>事件日志</h4>
            <div class="events-list">${eventsHtml || '<div class="text-muted">暂无事件</div>'}</div>
        </div>
        ${sub.error_message ? `<div class="detail-section error-section">
            <h4>错误信息</h4>
            <pre>${sub.error_message}</pre>
        </div>` : ''}
    `;

    showModal();
}
```

- [ ] **Step 4: 提交前端变更**

```bash
git add backend/static/admin/index.html
git commit -m "feat(ui): 更新管理后台支持极简工作流

- 添加进度条显示
- 更新状态标签
- 添加工作流步骤详情展示
- 添加重试按钮

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 6: 测试和清理

### Task 6.1: 更新测试

**Files:**
- Modify: `backend/tests/test_admin_submissions.py`
- Modify: `backend/tests/test_submission_tasks.py`

- [ ] **Step 1: 更新测试文件**

移除与 Issue/PR/审批相关的测试，添加新工作流测试。

- [ ] **Step 2: 运行测试**

```bash
cd backend && py -m pytest tests/ -v --tb=short
```

- [ ] **Step 3: 提交测试变更**

```bash
git add backend/tests/
git commit -m "test: 更新测试适配极简工作流

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

### Task 6.2: 最终清理和提交

- [ ] **Step 1: 运行语法检查**

```bash
cd backend && py -m py_compile app/**/*.py
```

- [ ] **Step 2: 检查未跟踪文件**

```bash
git status
```

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "refactor: 完成极简工作流重构

- 简化状态枚举和模型
- 创建 WorkflowService 执行三步工作流
- 简化 API 接口
- 移除不需要的服务和任务
- 更新前端 UI

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 验证清单

- [ ] 创建提交时只需 repo_url
- [ ] 点击"开始"能启动工作流
- [ ] 工作流能正确执行三个步骤
- [ ] 进度条正确显示
- [ ] 失败时能显示错误原因
- [ ] 能重试单个步骤
- [ ] 定时任务正常工作
