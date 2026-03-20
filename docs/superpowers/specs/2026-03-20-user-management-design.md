# 用户管理模块设计文档

> 创建日期：2026-03-20
> 状态：待实现

## 1. 概述

为 SkillHub 系统设计用户管理模块，实现基于工号 + API 密钥的认证方式，支持管理员后台管理用户。

### 1.1 核心需求

- 超级管理员通过 .env 配置，无公开注册功能
- 用户使用工号 + API 密钥登录
- 三层角色权限：super_admin > admin > user
- 完整的登录日志记录
- 管理后台支持用户 CRUD、批量导入导出

### 1.2 技术方案

采用**渐进式改造**方案，在现有 backend 项目基础上：
- 替换现有 User 模型
- 修改认证逻辑
- 新增管理后台 API
- 新增前端管理页面

---

## 2. 数据库设计

### 2.1 users 表（替换现有）

```sql
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id VARCHAR(20) NOT NULL UNIQUE COMMENT '工号',
    api_key VARCHAR(255) NOT NULL COMMENT 'API密钥(加密存储)',
    name VARCHAR(100) COMMENT '姓名',
    role ENUM('super_admin', 'admin', 'user') NOT NULL DEFAULT 'user',
    status ENUM('active', 'disabled') NOT NULL DEFAULT 'active',
    department VARCHAR(100) COMMENT '部门',
    team VARCHAR(100) COMMENT '团队',
    group_name VARCHAR(100) COMMENT '分组',
    skills_count INT DEFAULT 0 COMMENT '上传技能数',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_login TIMESTAMP NULL COMMENT '最后登录时间',

    INDEX idx_employee_id (employee_id),
    INDEX idx_status (status),
    INDEX idx_role (role)
);
```

### 2.2 login_logs 表（新增）

```sql
CREATE TABLE login_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id VARCHAR(20) NOT NULL COMMENT '工号',
    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('success', 'failed') NOT NULL,
    ip_address VARCHAR(45) COMMENT 'IP地址',
    user_agent VARCHAR(500) COMMENT '浏览器信息',
    device_id VARCHAR(100) COMMENT '设备标识',
    failure_reason VARCHAR(100) COMMENT '失败原因',

    INDEX idx_employee_id (employee_id),
    INDEX idx_login_time (login_time),
    INDEX idx_status (status)
);
```

---

## 3. API 设计

### 3.1 认证相关 `/api/auth`

| 端点 | 方法 | 权限 | 描述 |
|------|------|------|------|
| `/login` | POST | 公开 | 工号 + API 密钥登录 |
| `/logout` | POST | 登录 | 退出登录 |
| `/me` | GET | 登录 | 获取当前用户信息 |
| `/me/password` | PUT | 登录 | 修改自己的 API 密钥 |

**登录请求体：**
```json
{
    "employee_id": "w00000001",
    "api_key": "your-api-key"
}
```

**登录响应：**
```json
{
    "success": true,
    "token": "jwt-token-here",
    "user": {
        "id": 1,
        "employee_id": "w00000001",
        "name": "张三",
        "role": "admin"
    }
}
```

### 3.2 用户管理 `/api/admin/users`（admin/super_admin）

| 端点 | 方法 | 描述 |
|------|------|------|
| `/` | GET | 用户列表（分页、筛选） |
| `/` | POST | 新增用户 |
| `/{id}` | GET | 获取用户详情 |
| `/{id}` | PUT | 编辑用户 |
| `/{id}` | DELETE | 删除用户 |
| `/{id}/reset-key` | POST | 重置用户 API 密钥 |
| `/{id}/toggle-status` | POST | 切换启用/禁用状态 |
| `/import` | POST | 批量导入用户（CSV） |
| `/export` | GET | 导出用户列表 |

**用户列表查询参数：**
- `page`: 页码（默认 1）
- `page_size`: 每页数量（默认 20）
- `employee_id`: 工号筛选
- `name`: 姓名筛选（模糊）
- `role`: 角色筛选
- `status`: 状态筛选

### 3.3 登录日志 `/api/admin/login-logs`（admin/super_admin）

| 端点 | 方法 | 描述 |
|------|------|------|
| `/` | GET | 日志列表（分页、筛选） |

**查询参数：**
- `page`: 页码
- `page_size`: 每页数量
- `employee_id`: 工号筛选
- `status`: 登录状态筛选（success/failed）
- `start_date`: 开始日期
- `end_date`: 结束日期

---

## 4. 前端设计

### 4.1 登录页面改造

在现有登录框上方增加提示信息：

```
💡 请输入您的工号和 API 密钥登录系统
   如需账号，请联系管理员
```

表单字段：
- 工号（employee_id）
- API 密钥（api_key，密码类型输入框）

### 4.2 管理后台页面

**导航结构：**
- 用户管理
- 登录日志

**用户管理页面功能：**
- 搜索筛选（工号、姓名、状态）
- 新增用户按钮
- 批量导入按钮
- 导出按钮
- 用户列表表格（分页）
- 行操作：编辑、启用/禁用、删除

**用户新增/编辑弹窗字段：**
- 工号（必填）
- 姓名（必填）
- API 密钥（新增时必填，编辑时可选）
- 角色（下拉选择）
- 部门
- 团队
- 分组
- 状态

**批量导入格式（CSV）：**
```csv
employee_id,name,api_key,role,department,team,group_name
w00000001,张三,xxx-api-key,admin,研发部,后端组,A组
w00000002,李四,yyy-api-key,user,测试部,测试组,B组
```

---

## 5. 配置与安全

### 5.1 环境变量配置

```env
# 超级管理员配置
SUPER_ADMIN_EMPLOYEE_ID=w00000001
SUPER_ADMIN_API_KEY=your-secure-api-key-here
SUPER_ADMIN_NAME=系统管理员

# 安全配置
SECRET_KEY=your-jwt-secret-key
API_KEY_MIN_LENGTH=32
SESSION_EXPIRE_HOURS=24

# 登录安全
MAX_LOGIN_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=30
```

### 5.2 安全措施

| 措施 | 说明 |
|------|------|
| API 密钥加密 | 使用 bcrypt 哈希存储，不明文保存 |
| JWT Token | 登录成功后签发，有效期 24 小时 |
| 登录限流 | 同一 IP 5 次失败后锁定 30 分钟 |
| 操作日志 | 管理员操作记录到 login_logs |
| 权限校验 | 每个接口验证角色权限 |

### 5.3 权限矩阵

| 功能 | super_admin | admin | user |
|------|:-----------:|:-----:|:----:|
| 用户列表 | ✅ | ✅ | ❌ |
| 新增/编辑用户 | ✅ | ✅ | ❌ |
| 删除用户 | ✅ | ✅ | ❌ |
| 查看/导出日志 | ✅ | ✅ | ❌ |
| 上传技能 | ✅ | ✅ | ✅ |
| 管理自己技能 | ✅ | ✅ | ✅ |

### 5.4 超级管理员初始化

系统启动时自动检查并创建超级管理员：

1. 读取 .env 中的 `SUPER_ADMIN_EMPLOYEE_ID`、`SUPER_ADMIN_API_KEY`、`SUPER_ADMIN_NAME`
2. 查询数据库是否存在该工号的用户
3. 不存在则创建，角色为 `super_admin`
4. 存在则更新 API 密钥（确保与 .env 一致）

---

## 6. 文件结构

```
backend/
├── app/
│   ├── models/
│   │   ├── user.py          # 修改：新的 User 模型
│   │   └── login_log.py     # 新增：登录日志模型
│   ├── api/
│   │   ├── auth.py          # 修改：新的登录逻辑
│   │   └── admin.py         # 新增：管理后台 API
│   ├── schemas/
│   │   ├── user.py          # 新增：用户数据模型
│   │   └── login_log.py     # 新增：日志数据模型
│   └── config.py            # 修改：新增配置项
└── requirements.txt         # 修改：新增依赖

docs/
├── admin/                   # 新增：管理后台页面
│   ├── index.html
│   ├── users.html
│   └── logs.html
└── assets/
    └── admin.js             # 新增：管理后台 JS
```

---

## 7. 实现优先级

1. **P0 - 核心功能**
   - 数据库表创建
   - User 模型替换
   - 登录接口改造
   - 超级管理员初始化

2. **P1 - 管理功能**
   - 用户列表/新增/编辑/删除 API
   - 前端管理页面
   - 登录日志记录

3. **P2 - 增强功能**
   - 批量导入/导出
   - 登录限流
   - API 密钥重置
