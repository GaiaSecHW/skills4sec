# SecAgentHub API 接口文档

## 基础信息

- **Base URL**: `http://localhost:8000/api`
- **认证方式**: Bearer Token (JWT)
- **Content-Type**: `application/json`

## 通用响应格式

### 成功响应
```json
{
  "success": true,
  "data": { ... },
  "message": "操作成功"
}
```

### 错误响应
```json
{
  "code": "NOT_FOUND",
  "message": "资源不存在",
  "detail": { "id": 123 },
  "request_id": "abc123def456"
}
```

### 分页响应
```json
{
  "success": true,
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5,
  "data": [ ... ]
}
```

---

## 认证接口 `/api/auth`

### 登录（工号 + API 密钥）

```http
POST /api/auth/login/new
```

**请求体**:
```json
{
  "employee_id": "EMP001",
  "api_key": "your-api-key"
}
```

**响应**:
```json
{
  "success": true,
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": 1,
    "employee_id": "EMP001",
    "name": "张三",
    "role": "user",
    "status": "active",
    "department": "研发部",
    "team": "后端组",
    "group_name": "技能平台"
  }
}
```

### 刷新 Token

```http
POST /api/auth/refresh
```

**请求体**:
```json
{
  "refresh_token": "eyJ..."
}
```

**响应**:
```json
{
  "success": true,
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### 获取当前用户信息

```http
GET /api/auth/me
Authorization: Bearer {access_token}
```

**响应**: 返回当前用户信息

---

## 技能接口 `/api/skills`

### 获取技能列表

```http
GET /api/skills
```

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 20，最大 100 |
| category | string | 否 | 分类 slug |
| risk_level | string | 否 | 风险等级: safe/low/medium/high/critical |
| tool | string | 否 | 支持的工具: claude_code/codex/claude |
| search | string | 否 | 搜索关键词 |
| source_type | string | 否 | 来源类型: community/official |

**响应**:
```json
{
  "items": [
    {
      "id": 1,
      "slug": "my-skill",
      "name": "My Skill",
      "icon": "📦",
      "description": "技能描述",
      "summary": "简短摘要",
      "version": "1.0.0",
      "author": "作者名",
      "category": "productivity",
      "tags": ["效率", "开发"],
      "risk_level": "safe",
      "source_url": "https://github.com/...",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

### 获取技能详情

```http
GET /api/skills/{slug}
```

**响应**: 包含技能详情、审计信息、内容信息

### 创建技能

```http
POST /api/skills
Authorization: Bearer {access_token}
```

**请求体**: 见 `SkillCreate` Schema

### 更新技能

```http
PATCH /api/skills/{slug}
Authorization: Bearer {access_token}
```

### 删除技能

```http
DELETE /api/skills/{slug}
Authorization: Bearer {access_token}
```

### 获取分类列表

```http
GET /api/skills/categories/list
```

### 获取热门标签

```http
GET /api/skills/tags/popular?limit=20
```

---

## 提交接口 `/api/submissions`

### 提交技能

```http
POST /api/submissions
```

**请求体**:
```json
{
  "name": "技能名称",
  "repo_url": "https://github.com/user/skill-repo",
  "description": "技能描述",
  "category": "productivity",
  "contact": "联系方式"
}
```

**响应**:
```json
{
  "success": true,
  "message": "技能提交成功！请等待审核。",
  "submission_id": "uuid-xxx",
  "issue_url": "https://gitea.example.com/owner/repo/issues/123",
  "issue_number": 123
}
```

### 查询提交状态

```http
GET /api/submissions/{submission_id}/status
```

### 检查服务配置

```http
GET /api/submissions/health
```

---

## 审计接口 `/api/audit`

### 获取审计报告列表

```http
GET /api/audit/
```

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| skip | int | 跳过记录数 |
| limit | int | 返回记录数 |
| risk_level | string | 风险等级筛选 |
| is_blocked | bool | 是否被阻止 |

### 获取审计统计

```http
GET /api/audit/stats
```

**响应**:
```json
{
  "total": 100,
  "by_risk_level": {
    "safe": 60,
    "low": 20,
    "medium": 15,
    "high": 4,
    "critical": 1
  },
  "blocked": 5
}
```

### 获取单个审计报告

```http
GET /api/audit/{audit_id}
```

### 创建审计报告

```http
POST /api/audit/
Authorization: Bearer {access_token}
```

### 更新审计报告

```http
PUT /api/audit/{audit_id}
Authorization: Bearer {access_token}
```

### 删除审计报告

```http
DELETE /api/audit/{audit_id}
Authorization: Bearer {access_token}
```

### 获取安全发现列表

```http
GET /api/audit/{audit_id}/findings
```

### 添加安全发现

```http
POST /api/audit/{audit_id}/findings
Authorization: Bearer {access_token}
```

### 获取风险因素证据

```http
GET /api/audit/{audit_id}/risk-factors
```

### 导出审计报告

```http
GET /api/audit/{audit_id}/export?format=json
```

---

## 管理员接口 `/api/admin`

> 需要管理员或超级管理员权限

### 用户管理

#### 获取用户列表

```http
GET /api/admin/users
Authorization: Bearer {admin_token}
```

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| page | int | 页码 |
| page_size | int | 每页数量 |
| role | string | 角色筛选: user/admin/super_admin |
| status | string | 状态筛选: active/disabled |
| department | string | 部门筛选 |
| keyword | string | 关键词搜索 |

#### 创建用户

```http
POST /api/admin/users
Authorization: Bearer {admin_token}
```

**请求体**:
```json
{
  "employee_id": "EMP002",
  "name": "李四",
  "api_key": "secure-api-key",
  "role": "user",
  "department": "研发部",
  "team": "前端组",
  "group_name": "技能平台"
}
```

#### 获取用户详情

```http
GET /api/admin/users/{user_id}
Authorization: Bearer {admin_token}
```

#### 更新用户

```http
PUT /api/admin/users/{user_id}
Authorization: Bearer {admin_token}
```

**请求体**:
```json
{
  "name": "新名称",
  "api_key": "new-api-key",
  "role": "admin",
  "status": "active",
  "department": "新部门"
}
```

#### 删除用户

```http
DELETE /api/admin/users/{user_id}
Authorization: Bearer {admin_token}
```

#### 重置用户 API 密钥

```http
POST /api/admin/users/{user_id}/reset-key
Authorization: Bearer {admin_token}
```

**响应**:
```json
{
  "success": true,
  "message": "API密钥已重置",
  "data": {
    "employee_id": "EMP001",
    "new_api_key": "generated-secure-key"
  }
}
```

#### 切换用户状态

```http
POST /api/admin/users/{user_id}/toggle-status
Authorization: Bearer {admin_token}
```

#### 批量创建用户

```http
POST /api/admin/users/batch
Authorization: Bearer {super_admin_token}
```

**请求体**: 最多 100 个用户的数组

#### 导入用户 CSV

```http
POST /api/admin/users/import
Authorization: Bearer {super_admin_token}
Content-Type: multipart/form-data
```

**表单字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| file | File | CSV 文件 |
| generate_key | bool | 是否自动生成 API 密钥 |

#### 导出用户 CSV

```http
GET /api/admin/users/export
Authorization: Bearer {admin_token}
```

### 日志查询

#### 查询登录日志

```http
GET /api/admin/login-logs
Authorization: Bearer {admin_token}
```

**查询参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| page | int | 页码 |
| page_size | int | 每页数量 |
| employee_id | string | 工号筛选 |
| status | string | 状态筛选: success/failed |
| start_date | datetime | 开始时间 |
| end_date | datetime | 结束时间 |

#### 查询管理员操作日志

```http
GET /api/admin/admin-logs
Authorization: Bearer {super_admin_token}
```

### 提交管理

#### 获取提交列表

```http
GET /api/admin/submissions
Authorization: Bearer {admin_token}
```

#### 获取提交统计

```http
GET /api/admin/submissions/stats
Authorization: Bearer {admin_token}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "total": 100,
    "pending": 20,
    "processing": 10,
    "completed": 65,
    "failed": 5,
    "by_status": { ... },
    "by_risk": { ... },
    "today_count": 5,
    "avg_processing_time_seconds": 120.5
  }
}
```

#### 获取失败提交列表

```http
GET /api/admin/submissions/failed
Authorization: Bearer {admin_token}
```

#### 获取提交详情

```http
GET /api/admin/submissions/{submission_id}
Authorization: Bearer {admin_token}
```

#### 重试提交

```http
POST /api/admin/submissions/{submission_id}/retry
Authorization: Bearer {admin_token}
```

**请求体**:
```json
{
  "reset_count": false
}
```

#### 审批通过

```http
POST /api/admin/submissions/{submission_id}/approve
Authorization: Bearer {admin_token}
```

#### 拒绝提交

```http
POST /api/admin/submissions/{submission_id}/reject
Authorization: Bearer {admin_token}
```

**请求体**:
```json
{
  "reason": "拒绝原因"
}
```

#### 强制处理

```http
POST /api/admin/submissions/{submission_id}/force-process
Authorization: Bearer {super_admin_token}
```

#### 批量重试

```http
POST /api/admin/submissions/batch-retry
Authorization: Bearer {admin_token}
```

**请求体**:
```json
{
  "submission_ids": [1, 2, 3]
}
```

#### 导出提交 CSV

```http
GET /api/admin/submissions/export/csv
Authorization: Bearer {admin_token}
```

#### 获取提交趋势

```http
GET /api/admin/submissions/trends?days=7
Authorization: Bearer {admin_token}
```

#### 获取调度器状态

```http
GET /api/admin/submissions/scheduler/status
Authorization: Bearer {admin_token}
```

#### 手动触发定时任务

```http
POST /api/admin/submissions/scheduler/run-task
Authorization: Bearer {super_admin_token}
```

**请求体**:
```json
{
  "task_name": "sync_gitea_status"
}
```

---

## 健康检查

### 基础健康检查

```http
GET /health
```

**响应**:
```json
{
  "status": "healthy",
  "database": {
    "status": "healthy",
    "database": "connected"
  },
  "version": "1.0.0"
}
```

### API 根路径

```http
GET /
```

**响应**:
```json
{
  "name": "SecAgentHub API",
  "version": "1.0.0",
  "docs": "/docs",
  "redoc": "/redoc"
}
```

---

## 错误码说明

| 错误码 | HTTP 状态码 | 说明 |
|--------|-------------|------|
| NOT_FOUND | 404 | 资源不存在 |
| VALIDATION_ERROR | 422 | 数据验证失败 |
| UNAUTHORIZED | 401 | 未授权 |
| FORBIDDEN | 403 | 权限不足 |
| CONFLICT | 409 | 资源冲突 |
| DATABASE_ERROR | 500 | 数据库错误 |
| HTTP_ERROR | 4xx/5xx | HTTP 错误 |

---

## 角色权限说明

| 角色 | 说明 | 权限 |
|------|------|------|
| user | 普通用户 | 查看、提交技能 |
| admin | 管理员 | 用户管理、提交审批、日志查看 |
| super_admin | 超级管理员 | 全部权限 + 批量操作 + 系统管理 |

---

## 在线文档

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
