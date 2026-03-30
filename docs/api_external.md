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

---

## 1. 技能列表

获取技能市场中的技能列表，支持分页和模糊查询。

**接口地址：** `GET /api/skills`

**请求参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| page | int | 否 | 1 | 页码，从1开始 |
| page_size | int | 否 | 20 | 每页数量，最大100 |
| search | string | 否 | - | 模糊搜索关键词（搜索名称、描述、摘要） |
| category | string | 否 | - | 分类slug |
| risk_level | string | 否 | - | 风险等级：`safe`/`low`/`medium`/`high`/`critical` |
| tool | string | 否 | - | 支持的工具：`claude`/`codex`/`claude-code` |
| source_type | string | 否 | - | 来源类型：`official`/`community` |

**响应示例：**

```json
{
  "items": [
    {
      "id": 1,
      "slug": "code-reviewer",
      "name": "代码审查助手",
      "icon": "🔍",
      "description": "专业的代码审查技能...",
      "summary": "自动化代码审查",
      "version": "1.0.0",
      "author": "张三",
      "license": "MIT",
      "category": "development",
      "tags": ["review", "quality"],
      "supported_tools": ["claude", "claude-code"],
      "risk_factors": [],
      "risk_level": "safe",
      "is_blocked": false,
      "safe_to_publish": true,
      "source_url": "https://github.com/example/code-reviewer",
      "source_type": "community",
      "generated_at": "2025-01-15T10:30:00",
      "created_at": "2025-01-15T10:30:00",
      "updated_at": "2025-02-20T14:00:00"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

---

## 2. 技能详情

获取单个技能的详细信息，包括安全审计报告和内容。

**接口地址：** `GET /api/skills/{slug}`

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| slug | string | 是 | 技能唯一标识 |

**响应示例：**

```json
{
  "id": 1,
  "slug": "code-reviewer",
  "name": "代码审查助手",
  "icon": "🔍",
  "description": "专业的代码审查技能...",
  "summary": "自动化代码审查",
  "version": "1.0.0",
  "author": "张三",
  "license": "MIT",
  "category": "development",
  "tags": ["review", "quality"],
  "supported_tools": ["claude", "claude-code"],
  "risk_factors": [],
  "risk_level": "safe",
  "is_blocked": false,
  "safe_to_publish": true,
  "source_url": "https://github.com/example/code-reviewer",
  "source_type": "community",
  "generated_at": "2025-01-15T10:30:00",
  "created_at": "2025-01-15T10:30:00",
  "updated_at": "2025-02-20T14:00:00",
  "audit": {
    "id": 1,
    "skill_id": 1,
    "risk_level": "safe",
    "is_blocked": false,
    "safe_to_publish": true,
    "summary": "该技能通过安全审计",
    "files_scanned": 15,
    "total_lines": 1234,
    "audit_model": "claude-sonnet-4",
    "audited_at": "2025-01-16T08:00:00",
    "risk_factors": [],
    "findings": [],
    "risk_evidence": []
  },
  "content": {
    "id": 1,
    "skill_id": 1,
    "user_title": "代码审查助手",
    "value_statement": "帮助开发者快速发现代码问题",
    "actual_capabilities": ["发现常见代码异味", "建议代码优化"],
    "limitations": ["无法检测业务逻辑错误"],
    "best_practices": ["定期进行代码审查"],
    "anti_patterns": ["不要依赖AI完全替代人工审查"],
    "use_cases": [
      {
        "id": 1,
        "title": "PR审查",
        "description": "审查Pull Request",
        "target_user": "开发者"
      }
    ],
    "prompt_templates": [
      {
        "id": 1,
        "title": "基础审查",
        "scenario": "代码审查",
        "prompt": "请审查以下代码..."
      }
    ],
    "output_examples": [
      {
        "id": 1,
        "input_text": "def foo():\n    pass",
        "output_text": "发现1个问题..."
      }
    ],
    "faq": [
      {
        "id": 1,
        "question": "支持哪些语言?",
        "answer": "支持Python、JavaScript等主流语言"
      }
    ]
  }
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

下载技能完整包（ZIP格式），下载后计数自动+1。

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

## 接口变更日志

| 日期 | 版本 | 变更说明 |
|------|------|---------|
| 2026-03-30 | v1.0 | 初始版本，包含技能CRUD、下载、统计接口 |
