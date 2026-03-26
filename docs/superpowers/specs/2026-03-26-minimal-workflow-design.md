# 极简工作流设计文档

> 创建日期: 2026-03-26
> 状态: 已批准

## 概述

简化技能提交流程，移除 Issue 审批和 PR 合并流程，实现从 Git URL 直接到技能入库的极简工作流。

## 核心流程

```
Git URL → 克隆仓库 → 生成报告 → 迁移文件 → 完成
```

### 工作流状态

```
PENDING → CLONING → GENERATING → MIGRATING → COMPLETED
           ↓           ↓           ↓
        FAILED      FAILED      FAILED
```

### 步骤说明

| 步骤 | 输入 | 输出 | 操作 |
|------|------|------|------|
| 克隆 | repo_url | 本地目录 | git clone --depth 1 到 backend/skills_download/ |
| 生成 | 本地目录 | skill-report.json | 执行 skill-report-generator/generate.py |
| 迁移 | 技能目录 | skills/{author}/{name}/ | 复制到目标目录 |

## 数据模型变更

### Submission 模型简化

**删除字段**：

| 字段 | 原因 |
|------|------|
| issue_number | 不再使用 Issue |
| issue_url | 不再使用 Issue |
| issue_state | 不再使用 Issue |
| issue_labels | 不再使用 Issue |
| pr_number | 不再使用 PR |
| pr_url | 不再使用 PR |
| pr_state | 不再使用 PR |
| pr_merged | 不再使用 PR |
| approved_by | 移除审批流程 |
| approved_at | 移除审批流程 |
| approved_by_employee_id | 移除审批流程 |
| rejected_by | 移除审批流程 |
| rejected_at | 移除审批流程 |
| rejected_by_employee_id | 移除审批流程 |
| reject_reason | 移除审批流程 |
| workflow_run_id | 不再使用 Gitea Actions |
| workflow_run_url | 不再使用 Gitea Actions |

**新增字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| current_step | CharField(20) | 当前步骤：cloning/generating/migrating/completed |
| step_details | JSONField | 每步详细状态：`{"cloning": {"status": "completed", "duration": 2.3, ...}, ...}` |

**保留字段**：

- id, submission_id, name, repo_url, description, category, contact
- status (简化状态值)
- skill_count, processed_skills, failed_skills, skill_slugs
- highest_risk, error_code, error_message, error_details
- retry_count, max_retries, next_retry_at, last_retry_at
- created_at, updated_at, processing_started_at, processing_completed_at, completed_at

### SubmissionStatus 枚举简化

```python
class SubmissionStatus(str, Enum):
    PENDING = "pending"           # 待处理
    CLONING = "cloning"           # 克隆中
    GENERATING = "generating"     # 生成报告中
    MIGRATING = "migrating"       # 迁移中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败
```

### SubmissionEventType 枚举简化

```python
class SubmissionEventType(str, Enum):
    CREATED = "created"
    CLONE_STARTED = "clone_started"
    CLONE_SUCCESS = "clone_success"
    CLONE_FAILED = "clone_failed"
    GENERATE_STARTED = "generate_started"
    GENERATE_SUCCESS = "generate_success"
    GENERATE_FAILED = "generate_failed"
    MIGRATE_STARTED = "migrate_started"
    MIGRATE_SUCCESS = "migrate_success"
    MIGRATE_FAILED = "migrate_failed"
    COMPLETED = "completed"
    RETRY = "retry"
```

## API 变更

### 保留的 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /admin/submissions | 提交列表（支持状态筛选） |
| GET | /admin/submissions/{id} | 提交详情（含步骤和事件） |
| POST | /admin/submissions | 创建提交（只需 repo_url） |
| POST | /admin/submissions/{id}/start | 开始处理 |
| POST | /admin/submissions/{id}/retry-step | 重试单个步骤 |
| DELETE | /admin/submissions/{id} | 删除提交 |

### 删除的 API

| 方法 | 路径 | 原因 |
|------|------|------|
| POST | /{id}/approve | 移除审批流程 |
| POST | /{id}/reject | 移除审批流程 |
| POST | /{id}/force-process | 简化为 /start |
| GET | /{id}/workflow-progress | 合并到详情接口 |
| GET | /failed | 合并到列表筛选 |
| POST | /batch-retry | 暂不需要 |
| GET | /export/csv | 暂不需要 |
| GET | /scheduler/status | 删除定时任务 |
| POST | /scheduler/run-task | 删除定时任务 |

### 新增 API 详情

**POST /admin/submissions/{id}/start**

开始处理提交，自动执行所有步骤。

请求：
```json
{}
```

响应：
```json
{
  "success": true,
  "message": "工作流已启动",
  "data": {
    "submission_id": 123,
    "status": "cloning",
    "current_step": "cloning"
  }
}
```

**POST /admin/submissions/{id}/retry-step**

重试失败的步骤。

请求：
```json
{
  "step": "cloning"  // cloning | generating | migrating
}
```

响应：
```json
{
  "success": true,
  "message": "步骤重试中",
  "data": {
    "submission_id": 123,
    "status": "cloning",
    "current_step": "cloning"
  }
}
```

## 服务层设计

### WorkflowService

负责执行工作流的各个步骤。

```python
class WorkflowService:
    async def start_workflow(self, submission: Submission) -> bool:
        """启动完整工作流"""

    async def execute_step(self, submission: Submission, step: str) -> tuple[bool, str]:
        """执行单个步骤"""

    async def clone_repo(self, submission: Submission) -> tuple[bool, str, str]:
        """克隆仓库，返回 (成功, 消息, 本地路径)"""

    async def generate_report(self, submission: Submission, local_path: str) -> tuple[bool, str]:
        """生成审计报告"""

    async def migrate_files(self, submission: Submission, local_path: str) -> tuple[bool, str]:
        """迁移文件到目标目录"""
```

### 删除的服务

- `IssueHandler` - Issue 处理
- `GiteaSyncService` - Gitea 同步
- `RetryService` 中的自动重试逻辑（保留手动重试）

## 定时任务变更

### 删除的定时任务

| 任务 | 原因 |
|------|------|
| process_new_submissions | 不再轮询 Issue |
| sync_gitea_status | 不再同步 Gitea |
| process_pending_retries | 移除自动重试 |

### 保留的定时任务

| 任务 | 间隔 | 说明 |
|------|------|------|
| cleanup_old_events | 1小时 | 清理90天前的事件日志 |
| cleanup_stale_submissions | 1天 | 标记超时的提交为失败 |
| generate_daily_stats | 1天 | 生成每日统计 |

## 管理后台 UI

### 提交列表

```
┌─────────────────────────────────────────────────────────────┐
│ 技能提交管理                              [+ 新建提交]      │
├─────────────────────────────────────────────────────────────┤
│ 状态筛选: [全部▼] [进行中] [已完成] [失败]    搜索: [____] │
├─────────────────────────────────────────────────────────────┤
│ 名称          │ Git URL          │ 进度    │ 状态  │ 操作   │
├───────────────┼──────────────────┼─────────┼───────┼────────┤
│ python-tool   │ github.com/...   │ ████████│ 完成  │ [详情] │
│ skill-creator │ github.com/...   │ ███░░░░░│ 生成中│ [详情] │
│ my-skill      │ github.com/...   │ ██!░░░░░│ 失败  │ [重试] │
└─────────────────────────────────────────────────────────────┘
```

### 提交详情

```
┌─────────────────────────────────────────────────────────────┐
│ 提交详情 #123                                      [×]      │
├─────────────────────────────────────────────────────────────┤
│ 基本信息                                                    │
│   名称: python-tool                                         │
│   Git URL: https://github.com/user/python-tool              │
│   创建时间: 2026-03-26 10:30:00                             │
├─────────────────────────────────────────────────────────────┤
│ 工作流进度                                    [开始处理]    │
│                                                             │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐            │
│   │  ✓ 克隆  │───▶│ ✓ 生成   │───▶│ ○ 迁移   │            │
│   └──────────┘    └──────────┘    └──────────┘            │
│                                                             │
│   步骤详情:                                                 │
│   ● 克隆仓库 - 完成 (2.3s)                                  │
│   ● 生成报告 - 完成 (15.2s)                                 │
│   ● 迁移文件 - 进行中...                                    │
├─────────────────────────────────────────────────────────────┤
│ 事件日志                                                    │
│   10:30:15 [INFO] 开始克隆仓库                              │
│   10:30:17 [INFO] 克隆完成                                  │
│   10:30:18 [INFO] 开始生成报告                              │
│   10:30:33 [INFO] 报告生成完成                              │
└─────────────────────────────────────────────────────────────┘
```

## 文件目录结构

```
backend/
├── skills_download/          # 克隆的仓库（临时）
│   └── {author}/
│       └── {repo}/
│           └── skill-report.json
│
skills/                       # 最终技能目录
├── {author}/
│   └── {skill-name}/
│       ├── SKILL.md
│       ├── skill-report.json
│       └── ...
```

## 实现计划

### Phase 1: 数据模型简化

1. 更新 SubmissionStatus 枚举
2. 更新 SubmissionEventType 枚举
3. 添加新字段到 Submission 模型
4. 创建数据库迁移

### Phase 2: 服务层重构

1. 创建 WorkflowService
2. 删除 IssueHandler、GiteaSyncService
3. 简化 RetryService
4. 更新 submission_tasks.py

### Phase 3: API 简化

1. 更新 submissions.py 路由
2. 添加 start、retry-step 接口
3. 删除不需要的接口

### Phase 4: 前端更新

1. 更新管理后台列表页
2. 更新详情弹窗
3. 添加进度显示组件

### Phase 5: 清理

1. 删除无用代码
2. 更新测试
3. 更新文档
