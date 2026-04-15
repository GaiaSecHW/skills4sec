# SecAgentHub 外部API接口文档

> 本文档面向外部微服务对接方，所有接口**无需鉴权**即可访问。

---

## 目录

- [技能列表](#1-技能列表)
- [技能详情](#2-技能详情)
- [技能下载](#3-技能下载)
- [技能分类](#4-技能分类列表)
- [热门标签](#5-热门标签)
- [下载排行统计](#6-下载排行统计)
- [用户认证](#7-用户认证)
- [技能上传（Git URL）](#8-技能上传git-url)
- [技能上传（ZIP 文件）](#9-技能上传zip-文件)
- [查询提交状态](#10-查询提交状态)
- [我的提交记录](#11-我的提交记录)
- [上传流程总览](#12-上传流程总览)

---

## 1. 技能列表

获取技能市场中的技能列表，支持分页和模糊查询。

> **数据来源：** 直接读取 `docs/data/skills.json` 文件，非数据库查询。

**接口地址：** `GET /api/skills`

**请求参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| page | int | 否 | 1 | 页码，从1开始 |
| page_size | int | 否 | 20 | 每页数量，最大100 |
| search | string | 否 | - | 模糊搜索关键词（搜索名称、描述、摘要） |
| category | string | 否 | - | 分类slug，如 `cloud-security`、`billing-security`、`development` |
| risk_level | string | 否 | - | 风险等级：`safe`/`low`/`medium`/`high`/`critical` |
| tool | string | 否 | - | 支持的工具：`claude`/`codex`/`claude-code` |
| source_type | string | 否 | - | 来源类型：`official`/`community` |

**响应示例：**

```json
{
  "items": [
    {
      "id": 1,
      "slug": "skill-creator",
      "name": "skill-creator",
      "icon": "🛠️",
      "description": "Guide for creating effective skills...",
      "summary": "Guide for creating effective skills. This skill should be used when users want to create a new skill...",
      "version": "1.0.0",
      "author": "openai",
      "license": "Apache-2.0",
      "category": "documentation",
      "tags": ["skill-development", "codex", "workflow-automation", "documentation"],
      "supported_tools": ["claude", "codex", "claude-code"],
      "risk_factors": ["network", "external_commands", "filesystem"],
      "risk_level": "safe",
      "is_blocked": false,
      "safe_to_publish": true,
      "source_url": "https://github.com/openai/codex/tree/main/codex-rs/core/src/skills/assets/samples/skill-creator",
      "source_type": "official",
      "generated_at": "2026-01-17T08:05:38.741Z",
      "created_at": "2026-01-17T08:05:38.741Z",
      "updated_at": "2026-01-17T08:05:38.741Z"
    },
    {
      "id": 4,
      "slug": "cloud-api-internal-exposure",
      "name": "内部API外部暴露",
      "icon": "🔓",
      "description": "云服务将内部API注册至外部APIG或设为公开，导致高危管理接口可被任意调用。",
      "summary": "云服务将内部API注册至外部APIG或设为公开，导致高危管理接口可被任意调用。",
      "version": "1.0.0",
      "author": "icsl",
      "license": "Apache-2.0",
      "category": "api-security",
      "tags": ["cloud", "apig", "api-exposure", "misconfiguration"],
      "supported_tools": ["claude-code"],
      "risk_factors": ["network", "cloud_api"],
      "risk_level": "high",
      "is_blocked": false,
      "safe_to_publish": true,
      "source_url": "https://github.com/cxm95/skills4sec",
      "source_type": "community",
      "generated_at": "2026-03-16T00:00:00.000Z",
      "created_at": "2026-03-16T00:00:00.000Z",
      "updated_at": "2026-03-16T00:00:00.000Z"
    }
  ],
  "total": 26,
  "page": 1,
  "page_size": 20,
  "total_pages": 2
}
```

---

## 2. 技能详情

获取单个技能的详细信息，包括内容信息（如可用）。

> **数据来源：** 直接读取 `docs/data/skills.json` 文件。部分技能包含丰富的内容信息（use_cases、prompt_templates、faq等），部分仅有基础元数据。

**接口地址：** `GET /api/skills/{slug}`

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| slug | string | 是 | 技能唯一标识，如 `skill-creator`、`obs-anonymous-access-leak` |

**响应示例（含丰富内容的技能）：**

```json
{
  "id": 1,
  "slug": "skill-creator",
  "name": "skill-creator",
  "icon": "🛠️",
  "description": "Guide for creating effective skills...",
  "summary": "Guide for creating effective skills...",
  "version": "1.0.0",
  "author": "openai",
  "license": "Apache-2.0",
  "category": "documentation",
  "tags": ["skill-development", "codex", "workflow-automation", "documentation"],
  "supported_tools": ["claude", "codex", "claude-code"],
  "risk_factors": ["network", "external_commands", "filesystem"],
  "risk_level": "safe",
  "is_blocked": false,
  "safe_to_publish": true,
  "source_url": "https://github.com/openai/codex/...",
  "source_type": "official",
  "generated_at": "2026-01-17T08:05:38.741Z",
  "created_at": "2026-01-17T08:05:38.741Z",
  "updated_at": "2026-01-17T08:05:38.741Z",
  "audit": null,
  "content": {
    "id": 1,
    "skill_id": 1,
    "user_title": "Create skills for AI agents",
    "value_statement": "Creating specialized AI agents requires a structured approach...",
    "actual_capabilities": ["Initialize new skill directories...", "Validate skill structure..."],
    "limitations": ["This skill provides guidance only..."],
    "best_practices": [],
    "anti_patterns": [],
    "use_cases": [
      {"id": 0, "title": "Automate repetitive coding tasks", "description": "Create skills that bundle workflow scripts...", "target_user": "Software developers"}
    ],
    "prompt_templates": [
      {"id": 0, "title": "Create basic skill", "scenario": "Start a new skill project", "prompt": "Create a new skill called [skill-name]..."}
    ],
    "output_examples": [],
    "faq": [
      {"id": 0, "question": "Which platforms support this skill?", "answer": "The skill creator is designed for Codex but skills created work on Codex, Claude, and Claude Code."}
    ]
  }
}
```

**响应示例（仅基础元数据的技能）：**

```json
{
  "id": 4,
  "slug": "cloud-api-internal-exposure",
  "name": "内部API外部暴露",
  "icon": "🔓",
  "description": "云服务将内部API注册至外部APIG或设为公开，导致高危管理接口可被任意调用。",
  "summary": "云服务将内部API注册至外部APIG或设为公开，导致高危管理接口可被任意调用。",
  "version": "1.0.0",
  "author": "icsl",
  "license": "Apache-2.0",
  "category": "api-security",
  "tags": ["cloud", "apig", "api-exposure", "misconfiguration"],
  "supported_tools": ["claude-code"],
  "risk_factors": ["network", "cloud_api"],
  "risk_level": "high",
  "is_blocked": false,
  "safe_to_publish": true,
  "source_url": "https://github.com/cxm95/skills4sec",
  "source_type": "community",
  "generated_at": "2026-03-16T00:00:00.000Z",
  "created_at": "2026-03-16T00:00:00.000Z",
  "updated_at": "2026-03-16T00:00:00.000Z",
  "audit": null,
  "content": null
}
```

**错误响应：**

```json
{
  "detail": "Skill not found"
}
```

---

## 3. 技能下载

下载技能完整包（ZIP格式），直接从 `skills/` 目录打包。

> **数据来源：** 直接读取 `skills/{slug}/` 目录，打包为 ZIP 返回。需该技能在 `skills/` 目录下有对应文件夹。

**接口地址：** `GET /api/skills/{slug}/download`

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| slug | string | 是 | 技能唯一标识 |

**响应：** 返回 `application/zip` 格式的ZIP文件

**响应头：**

```
Content-Disposition: attachment; filename={slug}.zip
Content-Type: application/zip
```

**错误响应：**

```json
{
  "detail": "Skill directory not found: xxx"
}
```

---

## 4. 技能分类列表

获取所有技能分类及每个分类下的技能数量。

**接口地址：** `GET /api/skills/categories/list`

**请求参数：** 无

**响应示例：**

```json
[
  {
    "id": 1,
    "slug": "development",
    "name": "开发",
    "description": "开发辅助工具",
    "icon": "💻",
    "skill_count": 25
  },
  {
    "id": 2,
    "slug": "security",
    "name": "安全",
    "description": "安全检测工具",
    "icon": "🔒",
    "skill_count": 18
  }
]
```

---

## 5. 热门标签

获取使用最多的技能标签。

**接口地址：** `GET /api/skills/tags/popular`

**请求参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| limit | int | 否 | 20 | 返回数量，最大100 |

**响应示例：**

```json
[
  {"name": "code-review", "count": 45},
  {"name": "security", "count": 38},
  {"name": "testing", "count": 32}
]
```

---

## 6. 下载排行统计

获取技能下载排行榜，**无需认证**。

**接口地址：** `GET /api/stats/top`

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| start_date | string | 否 | 开始日期，格式：`YYYY-MM-DD` |
| end_date | string | 否 | 结束日期，格式：`YYYY-MM-DD` |

**响应示例：**

```json
{
  "period": {
    "start_date": "2025-02-01",
    "end_date": "2025-02-09"
  },
  "total_downloads": 1500,
  "rankings": [
    {
      "rank": 1,
      "skill_name": "代码审查助手",
      "downloads": 500,
      "author": "张三"
    },
    {
      "rank": 2,
      "skill_name": "安全扫描器",
      "downloads": 380,
      "author": "李四"
    },
    {
      "rank": 3,
      "skill_name": "测试生成器",
      "downloads": 280,
      "author": "王五"
    }
  ]
}
```

**响应字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| period | object | 统计周期 |
| period.start_date | string | 开始日期，未传则null |
| period.end_date | string | 结束日期，未传则null |
| total_downloads | int | 排行榜内技能的总下载次数 |
| rankings | array | 下载排行列表 |
| rankings[].rank | int | 排名 |
| rankings[].skill_name | string | 技能名称 |
| rankings[].downloads | int | 下载次数 |
| rankings[].author | string | 作者 |

---

## 通用说明

### 基础URL

```
http://{host}:{port}/api
```

示例：`http://localhost:8000/api`

### 响应格式

所有接口均返回JSON格式数据。

### 错误处理

错误响应统一格式：

```json
{
  "detail": "错误描述信息"
}
```

### 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 422 | 数据验证失败 |
| 500 | 服务器内部错误 |

---

## 7. 用户认证

上传技能前需要先登录获取 JWT Token，后续上传接口需要在 `Authorization` 请求头中携带 Token。

**接口地址：** `POST /api/auth/login`

**请求体：**

```json
{
  "employee_id": "工号",
  "api_key": "API密钥"
}
```

**响应示例：**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "employee_id": "10001",
    "role": "user"
  }
}
```

> 登录成功后，将 `access_token` 用于后续所有需要认证的接口：`Authorization: Bearer <access_token>`

---

## 8. 技能上传（Git URL）

通过 Git 仓库地址提交技能，系统会自动克隆仓库并生成安全报告。

**接口地址：** `POST /api/submissions`

**权限：** 需要用户登录（JWT Token）

**请求头：**

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**请求体：**

```json
{
  "name": "my-security-skill",
  "repo_url": "https://github.com/user/skill-repo",
  "description": "技能描述信息",
  "category": "security",
  "contact": "联系方式（可选）"
}
```

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 技能名称，1-200字符 |
| repo_url | string | 是 | Git 仓库地址，最大500字符 |
| description | string | 否 | 技能描述，最大2000字符 |
| category | string | 否 | 分类slug |
| contact | string | 否 | 联系方式 |

**响应示例（成功）：**

```json
{
  "success": true,
  "message": "技能提交成功！请等待审核。",
  "submission_id": "uuid-string",
  "issue_url": "https://gitea.example.com/owner/repo/issues/42",
  "issue_number": 42
}
```

**响应示例（Issue 创建暂时失败）：**

```json
{
  "success": true,
  "message": "技能已提交，但 Issue 创建暂时失败。系统会自动重试，请稍后查看状态。",
  "submission_id": "uuid-string"
}
```

**错误响应：**

| 状态码 | 说明 |
|--------|------|
| 401 | 未登录或 Token 过期 |
| 422 | 参数验证失败 |
| 500 | 服务未配置 Gitea Token |

---

## 9. 技能上传（ZIP 文件）

通过上传 ZIP 压缩包提交技能，ZIP 内必须包含 `SKILL.md` 文件。

**接口地址：** `POST /api/submissions/upload-zip`

**权限：** 需要用户登录（JWT Token）

**请求头：**

```
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

**请求参数（FormData）：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | File | 是 | ZIP 压缩包文件 |
| name | string | 否 | 技能名称（不填则从 SKILL.md 标题自动提取） |
| description | string | 否 | 技能描述 |
| category | string | 否 | 分类slug |
| contact | string | 否 | 联系方式 |

**ZIP 文件要求：**

- 文件扩展名必须为 `.zip`
- ZIP 内必须包含 `SKILL.md` 文件（可在子目录中）
- 系统会自动从 `SKILL.md` 的第一行 `# 标题` 提取技能名称

**响应示例：**

```json
{
  "success": true,
  "message": "ZIP 上传成功，工作流已启动",
  "data": {
    "submission_id": "uuid-string",
    "name": "my-skill-name",
    "status": "pending"
  }
}
```

**错误响应：**

| 状态码 | 说明 |
|--------|------|
| 401 | 未登录或 Token 过期 |
| 422 | 非ZIP文件 / ZIP内无SKILL.md / 无效ZIP文件 |

**调用示例（curl）：**

```bash
curl -X POST http://localhost:8000/api/submissions/upload-zip \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/skill-package.zip" \
  -F "name=my-skill" \
  -F "description=技能描述"
```

---

## 10. 查询提交状态

查询技能提交的当前处理状态，无需认证。

**接口地址：** `GET /api/submissions/{submission_id}/status`

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| submission_id | string | 是 | 提交时返回的 UUID |

**响应示例：**

```json
{
  "success": true,
  "data": {
    "submission_id": "uuid-string",
    "name": "my-security-skill",
    "status": "completed",
    "issue_number": 42,
    "issue_url": "https://gitea.example.com/owner/repo/issues/42",
    "pr_number": null,
    "pr_url": null,
    "error_message": null,
    "created_at": "2026-04-15T10:00:00",
    "updated_at": "2026-04-15T10:01:30"
  }
}
```

**状态值说明：**

| 状态 | 说明 |
|------|------|
| pending | 等待处理（ZIP 上传初始状态） |
| creating_issue | 正在创建 Gitea Issue |
| issue_created | Issue 创建成功 |
| issue_failed | Issue 创建失败（系统自动重试） |
| cloning | 正在克隆仓库 / 解压 ZIP |
| clone_completed | 克隆/解压完成 |
| clone_failed | 克隆/解压失败 |
| generating | 正在生成安全报告 |
| completed | 处理完成 |
| failed | 处理失败 |

---

## 11. 我的提交记录

获取当前登录用户的提交历史记录。

**接口地址：** `GET /api/submissions/my`

**权限：** 需要用户登录（JWT Token）

**请求头：**

```
Authorization: Bearer <access_token>
```

**响应示例：**

```json
{
  "success": true,
  "data": [
    {
      "submission_id": "uuid-string",
      "name": "my-security-skill",
      "status": "completed",
      "repo_url": "https://github.com/user/skill-repo",
      "source_type": "git",
      "issue_url": "https://gitea.example.com/owner/repo/issues/42",
      "created_at": "2026-04-15T10:00:00",
      "updated_at": "2026-04-15T10:01:30"
    }
  ]
}
```

---

## 12. 上传流程总览

### 方式一：Git URL 上传

```
用户登录 → POST /api/auth/login → 获取 JWT Token
    │
    ▼
提交 Git URL → POST /api/submissions
    │
    ├── 后端自动创建 Gitea Issue（pending-approval 标签）
    │
    ├── 启动后台工作流：
    │   │
    │   ├── Step 1: 克隆仓库（git clone / GitHub ZIP API）
    │   │      └── 验证 SKILL.md 存在
    │   │
    │   ├── Step 1.5: 复制到 skills_download/git/{name}/
    │   │
    │   └── Step 2: 执行 skill-report-generator 生成安全报告
    │          └── 输出 skill-report.json
    │
    └── 返回 submission_id → 用户轮询状态
         └── GET /api/submissions/{id}/status
```

### 方式二：ZIP 文件上传

```
用户登录 → POST /api/auth/login → 获取 JWT Token
    │
    ▼
上传 ZIP → POST /api/submissions/upload-zip
    │
    ├── 验证文件类型（.zip）
    ├── 保存到 skills_zip_temp/{uuid}.zip
    ├── 验证 ZIP 内含 SKILL.md
    └── 从 SKILL.md 标题提取技能名称
    │
    ▼
启动后台工作流：
    │
    ├── Step 1: 解压 ZIP → skills_download/zip/{name}/
    │      └── 递归查找 SKILL.md
    │
    ├── Step 1.5: 复制到 skills_download/git/{name}/
    │
    └── Step 2: 执行 skill-report-generator 生成安全报告
           └── 输出 skill-report.json
    │
    ▼
返回 submission_id → 用户轮询状态
 └── GET /api/submissions/{id}/status
```

### 失败重试机制

- Issue 创建失败：自动重试，间隔 60s → 300s → 900s（指数退避）
- 工作流步骤失败：管理员可通过后台接口手动重试单步或继续流程
- 定时任务 `process_pending_retries` 每 60 秒扫描待重试的提交

---

## 接口变更日志

| 日期 | 版本 | 变更说明 |
|------|------|---------|
| 2026-04-15 | v1.2 | 新增用户认证、技能上传（Git URL / ZIP）、提交状态查询、我的提交记录、上传流程总览文档 |
| 2026-03-30 | v1.1 | 技能列表、详情、下载接口改为直接读取 skills.json 和 skills 目录，不再依赖数据库 |
| 2026-03-30 | v1.0 | 初始版本，包含技能CRUD、下载、统计接口 |
