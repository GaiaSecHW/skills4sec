# 用户管理模块 - P2 增强功能实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现批量导入导出用户、登录限流、前端管理页面

**Architecture:** 添加 CSV 导入导出端点、内存限流中间件、前端 SPA 管理页面

**Tech Stack:** FastAPI, Tortoise ORM, CSV, SPA (原生 JS)

**前置条件:** P0 核心功能和 P1 管理功能已完成

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/api/admin.py` | 修改 | 添加批量导入导出端点 |
| `backend/app/utils/rate_limit.py` | 新建 | 登录限流工具 |
| `backend/app/api/auth.py` | 修改 | 添加登录限流 |
| `docs/assets/app.js` | 修改 | 添加管理后台前端 |

---

## Task 1: 创建登录限流工具

**Files:**
- Create: `backend/app/utils/rate_limit.py`

- [ ] **Step 1: 创建内存限流工具**

```python
# backend/app/utils/rate_limit.py
"""
登录限流工具（内存存储，单实例）

生产环境多实例部署建议使用 Redis 替代
"""
from datetime import datetime, timedelta
from typing import Dict, Tuple
from collections import defaultdict

from app.config import settings


# 存储结构: {ip: [(timestamp, success), ...]}
_login_attempts: Dict[str, list] = defaultdict(list)


def _cleanup_old_attempts(ip: str, window_minutes: int = None) -> None:
    """清理过期的登录记录"""
    if window_minutes is None:
        window_minutes = settings.LOGIN_LOCKOUT_MINUTES

    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
    _login_attempts[ip] = [
        (ts, success) for ts, success in _login_attempts[ip]
        if ts > cutoff
    ]


def record_login_attempt(ip: str, success: bool) -> None:
    """记录登录尝试"""
    if not ip:
        return
    _cleanup_old_attempts(ip)
    _login_attempts[ip].append((datetime.utcnow(), success))


def is_login_blocked(ip: str) -> Tuple[bool, int]:
    """
    检查 IP 是否被锁定

    Returns:
        (is_blocked, remaining_minutes)
    """
    if not ip:
        return False, 0

    _cleanup_old_attempts(ip)

    # 获取最近失败次数
    recent_failures = sum(1 for _, success in _login_attempts[ip] if not success)

    if recent_failures >= settings.MAX_LOGIN_ATTEMPTS:
        # 计算剩余锁定时间
        oldest_failure = min(ts for ts, success in _login_attempts[ip] if not success)
        unlock_time = oldest_failure + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
        remaining = (unlock_time - datetime.utcnow()).total_seconds() / 60
        return True, max(0, int(remaining))

    return False, 0


def clear_login_attempts(ip: str) -> None:
    """清除 IP 的登录记录（登录成功后调用）"""
    if ip in _login_attempts:
        del _login_attempts[ip]
```

- [ ] **Step 2: 验证语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.utils.rate_limit import record_login_attempt, is_login_blocked; print('Rate limit OK')"
```
Expected: `Rate limit OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/utils/rate_limit.py
git commit -m "feat(rate-limit): add in-memory login rate limiter

- Track login attempts per IP
- Block after MAX_LOGIN_ATTEMPTS failures
- Auto-cleanup expired attempts
- Single-instance only (use Redis for multi-instance)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 在登录端点添加限流

**Files:**
- Modify: `backend/app/api/auth.py`

- [ ] **Step 1: 添加限流逻辑到登录端点**

在导入部分添加：

```python
from app.utils.rate_limit import record_login_attempt, is_login_blocked, clear_login_attempts
```

在 `login_by_employee_id` 函数开头，获取 `client_ip` 之后添加限流检查：

```python
    # 检查登录限流
    blocked, remaining = is_login_blocked(client_ip)
    if blocked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录尝试过多，请 {remaining} 分钟后再试",
        )
```

在验证失败时记录失败尝试：

```python
    if not user:
        record_login_attempt(client_ip, success=False)
        await log_failure("工号不存在")
        # ... raise HTTPException

    if not user.api_key_hash or not verify_api_key(user_data.api_key, user.api_key_hash):
        record_login_attempt(client_ip, success=False)
        await log_failure("API 密钥错误")
        # ... raise HTTPException
```

在登录成功后清除记录：

```python
    # 登录成功，清除限流记录
    clear_login_attempts(client_ip)

    # 更新最后登录时间
    user.last_login = datetime.utcnow()
    await user.save()
```

- [ ] **Step 2: 验证语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.api.auth import login_by_employee_id; print('Auth with rate limit OK')"
```
Expected: `Auth with rate limit OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/auth.py
git commit -m "feat(auth): add login rate limiting

- Check IP block status before authentication
- Record failed login attempts
- Clear attempts on successful login
- Return 429 with remaining lockout time

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 添加用户导出端点

**Files:**
- Modify: `backend/app/api/admin.py`

- [ ] **Step 1: 添加 CSV 导出端点**

在导入部分添加：

```python
from fastapi.responses import StreamingResponse
import io
import csv
```

在文件末尾添加导出端点：

```python
# ============ 批量操作 ============

@router.get("/users/export")
async def export_users(
    employee_id: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    admin: User = Depends(get_current_admin_user)
):
    """导出用户列表为 CSV (管理员)"""
    query = User.all()

    if employee_id:
        query = query.filter(employee_id__icontains=employee_id)
    if role:
        query = query.filter(role=role)
    if status:
        query = query.filter(status=status)

    users = await query.order_by("employee_id")

    # 生成 CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # 表头
    writer.writerow([
        "employee_id", "name", "role", "status",
        "department", "team", "group_name", "skills_count",
        "last_login", "created_at"
    ])

    # 数据行
    for u in users:
        writer.writerow([
            u.employee_id,
            u.name or "",
            u.role,
            u.status,
            u.department or "",
            u.team or "",
            u.group_name or "",
            u.skills_count,
            u.last_login.isoformat() if u.last_login else "",
            u.created_at.isoformat(),
        ])

    output.seek(0)

    # 记录操作日志
    await AdminLog.create(
        admin_id=admin.id,
        admin_employee_id=admin.employee_id,
        action="export_users",
        details={"count": len(users)},
    )

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )
```

- [ ] **Step 2: 验证语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.api.admin import export_users; print('Export OK')"
```
Expected: `Export OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin.py
git commit -m "feat(admin): add user export to CSV endpoint

- Support same filters as user list
- Generate CSV with all user fields
- Log export operation

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 添加用户导入端点

**Files:**
- Modify: `backend/app/api/admin.py`

- [ ] **Step 1: 添加 CSV 导入端点**

在导入部分添加：

```python
from fastapi import UploadFile, File, Form
```

在 `export_users` 后添加导入端点：

```python
@router.post("/users/import")
async def import_users(
    file: UploadFile = File(...),
    conflict_strategy: str = Form("skip", pattern="^(skip|overwrite|raise)$"),
    validate_only: bool = Form(False),
    admin: User = Depends(get_current_admin_user)
):
    """
    批量导入用户 (管理员)

    conflict_strategy:
        - skip: 跳过已存在的工号
        - overwrite: 覆盖已存在的用户
        - raise: 遇到冲突报错

    validate_only: 仅验证不导入
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请上传 CSV 文件"
        )

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件编码必须是 UTF-8"
        )

    reader = csv.DictReader(io.StringIO(text))

    results = {
        "total": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
    }

    for row_num, row in enumerate(reader, start=2):  # 从第2行开始（第1行是表头）
        results["total"] += 1

        employee_id = row.get("employee_id", "").strip()
        name = row.get("name", "").strip()
        api_key = row.get("api_key", "").strip()
        role = row.get("role", "user").strip()
        department = row.get("department", "").strip() or None
        team = row.get("team", "").strip() or None
        group_name = row.get("group_name", "").strip() or None

        # 验证必填字段
        if not employee_id:
            results["errors"].append({
                "row": row_num,
                "employee_id": "",
                "reason": "工号不能为空"
            })
            continue

        if not name:
            results["errors"].append({
                "row": row_num,
                "employee_id": employee_id,
                "reason": "姓名不能为空"
            })
            continue

        # 验证 API 密钥（仅创建时）
        existing = await User.get_or_none(employee_id=employee_id)
        if not existing and not api_key:
            results["errors"].append({
                "row": row_num,
                "employee_id": employee_id,
                "reason": "新增用户必须提供 API 密钥"
            })
            continue

        if api_key:
            valid, msg = validate_api_key_complexity(api_key)
            if not valid:
                results["errors"].append({
                    "row": row_num,
                    "employee_id": employee_id,
                    "reason": msg
                })
                continue

        # 仅验证模式
        if validate_only:
            if existing:
                results["skipped"] += 1
            else:
                results["created"] += 1
            continue

        # 处理冲突
        if existing:
            if conflict_strategy == "skip":
                results["skipped"] += 1
                continue
            elif conflict_strategy == "raise":
                results["errors"].append({
                    "row": row_num,
                    "employee_id": employee_id,
                    "reason": f"工号已存在（conflict_strategy=raise）"
                })
                continue
            elif conflict_strategy == "overwrite":
                # 更新用户
                existing.name = name
                if api_key:
                    existing.api_key_hash = hash_api_key(api_key)
                if role in ("user", "admin", "super_admin"):
                    existing.role = role
                existing.department = department
                existing.team = team
                existing.group_name = group_name
                await existing.save()
                results["updated"] += 1
                continue

        # 创建新用户
        await User.create(
            employee_id=employee_id,
            name=name,
            api_key_hash=hash_api_key(api_key),
            role=role if role in ("user", "admin", "super_admin") else "user",
            department=department,
            team=team,
            group_name=group_name,
            status="active",
        )
        results["created"] += 1

    # 记录操作日志
    if not validate_only and (results["created"] > 0 or results["updated"] > 0):
        await AdminLog.create(
            admin_id=admin.id,
            admin_employee_id=admin.employee_id,
            action="import_users",
            details={
                "total": results["total"],
                "created": results["created"],
                "updated": results["updated"],
                "skipped": results["skipped"],
                "errors_count": len(results["errors"]),
            },
        )

    response = {
        "success": True,
        "total": results["total"],
        "created": results["created"],
        "updated": results["updated"],
        "skipped": results["skipped"],
        "errors": results["errors"],
    }

    if validate_only:
        response["valid"] = len(results["errors"]) == 0
        response["message"] = f"验证{'通过' if response['valid'] else '失败'}，共 {results['total']} 条记录"
    else:
        response["message"] = f"成功导入 {results['created'] + results['updated']} 条记录，跳过 {results['skipped']} 条"

    return response
```

- [ ] **Step 2: 验证语法**

```bash
cd D:/work/skillhub/skills4sec/backend && python -c "from app.api.admin import import_users; print('Import OK')"
```
Expected: `Import OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin.py
git commit -m "feat(admin): add user import from CSV endpoint

- Support conflict_strategy: skip/overwrite/raise
- Support validate_only mode
- Validate required fields and API key complexity
- Log import operation

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: 前端 - 添加管理后台路由和页面

**Files:**
- Modify: `docs/assets/app.js`

- [ ] **Step 1: 添加管理后台路由**

在 `getRoute` 函数中添加新路由：

```javascript
function getRoute() {
    const hash = location.hash.replace(/^#\/?/, '');
    if (!hash) return { page: 'home' };
    // ... 现有路由
    if (hash === 'admin/users' || hash.startsWith('admin/users?')) return { page: 'admin-users' };
    if (hash === 'admin/logs' || hash.startsWith('admin/logs?')) return { page: 'admin-logs' };
    return { page: 'home' };
}
```

- [ ] **Step 2: 在 render 函数中添加页面渲染**

```javascript
    // 在现有路由判断后添加
    } else if (route.page === 'admin-users') {
      main.innerHTML = renderAdminUsersPage();
      bindAdminUsersEvents();
    } else if (route.page === 'admin-logs') {
      main.innerHTML = renderAdminLogsPage();
      bindAdminLogsEvents();
    }
```

- [ ] **Step 3: 添加用户管理页面渲染函数**

```javascript
  /* ===================== ADMIN USERS PAGE ===================== */
  function renderAdminUsersPage() {
    return `
<div class="detail-page px-container max-w-7xl" style="padding-bottom:4rem">
  <div style="text-align:center;padding:2rem 0 1.5rem">
    <h1 style="font-size:2rem;font-weight:700;margin-bottom:.5rem">用户管理</h1>
    <p class="text-muted">管理系统用户、分配角色和权限</p>
  </div>

  <div class="admin-toolbar" style="display:flex;gap:.75rem;flex-wrap:wrap;margin-bottom:1.5rem">
    <input type="text" id="admin-search" class="form-input" placeholder="搜索工号或姓名..." style="flex:1;min-width:200px">
    <select id="admin-role-filter" class="form-input" style="width:auto">
      <option value="">全部角色</option>
      <option value="super_admin">超级管理员</option>
      <option value="admin">管理员</option>
      <option value="user">普通用户</option>
    </select>
    <select id="admin-status-filter" class="form-input" style="width:auto">
      <option value="">全部状态</option>
      <option value="active">启用</option>
      <option value="disabled">禁用</option>
    </select>
    <button class="btn-secondary" id="admin-export-btn">导出 CSV</button>
    <button class="btn-primary" id="admin-add-btn">+ 新增用户</button>
  </div>

  <div id="admin-users-table" class="admin-table-wrapper" style="overflow-x:auto">
    <p class="text-muted">加载中...</p>
  </div>

  <div id="admin-pagination" class="pagination" style="margin-top:1rem"></div>
</div>

<!-- 用户编辑弹窗 -->
<div id="user-modal" class="modal" style="display:none">
  <div class="modal-overlay" onclick="closeUserModal()"></div>
  <div class="modal-content">
    <div class="modal-header">
      <h3 id="user-modal-title">新增用户</h3>
      <button class="modal-close" onclick="closeUserModal()">&times;</button>
    </div>
    <form id="user-form">
      <input type="hidden" id="user-id">
      <div class="form-group">
        <label class="form-label">工号 *</label>
        <input type="text" id="user-employee-id" class="form-input" required pattern="^w[0-9]{8}$" placeholder="w00000001">
      </div>
      <div class="form-group">
        <label class="form-label">姓名 *</label>
        <input type="text" id="user-name" class="form-input" required>
      </div>
      <div class="form-group">
        <label class="form-label">API 密钥 <span id="api-key-hint" class="text-muted" style="font-weight:normal">(新增必填，至少32字符)</span></label>
        <input type="text" id="user-api-key" class="form-input" minlength="32">
      </div>
      <div class="form-group">
        <label class="form-label">角色</label>
        <select id="user-role" class="form-input">
          <option value="user">普通用户</option>
          <option value="admin">管理员</option>
          <option value="super_admin">超级管理员</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">部门</label>
        <input type="text" id="user-department" class="form-input">
      </div>
      <div class="form-group">
        <label class="form-label">团队</label>
        <input type="text" id="user-team" class="form-input">
      </div>
      <div class="form-group">
        <label class="form-label">分组</label>
        <input type="text" id="user-group" class="form-input">
      </div>
      <div class="modal-footer">
        <button type="button" class="btn-secondary" onclick="closeUserModal()">取消</button>
        <button type="submit" class="btn-primary">保存</button>
      </div>
    </form>
  </div>
</div>`;
  }
```

- [ ] **Step 4: 添加用户管理页面事件绑定**

```javascript
  function bindAdminUsersEvents() {
    const API_BASE = window.location.hostname === 'localhost' ? 'http://localhost:8001' : '';
    let token = localStorage.getItem('access_token');
    let currentSkip = 0;
    const limit = 20;

    if (!token) {
      document.getElementById('admin-users-table').innerHTML = '<p class="text-muted">请先登录</p>';
      return;
    }

    function loadUsers() {
      const search = document.getElementById('admin-search')?.value || '';
      const role = document.getElementById('admin-role-filter')?.value || '';
      const status = document.getElementById('admin-status-filter')?.value || '';

      let url = `${API_BASE}/api/admin/users?skip=${currentSkip}&limit=${limit}`;
      if (search) url += `&employee_id=${encodeURIComponent(search)}&name=${encodeURIComponent(search)}`;
      if (role) url += `&role=${role}`;
      if (status) url += `&status=${status}`;

      fetch(url, { headers: { 'Authorization': `Bearer ${token}` } })
        .then(r => r.json())
        .then(data => {
          if (data.detail) {
            document.getElementById('admin-users-table').innerHTML = `<p class="text-muted">${escHtml(data.detail)}</p>`;
            return;
          }
          renderUsersTable(data);
        })
        .catch(() => {
          document.getElementById('admin-users-table').innerHTML = '<p class="text-muted">加载失败</p>';
        });
    }

    function renderUsersTable(data) {
      const rows = data.items.map(u => `
        <tr>
          <td>${escHtml(u.employee_id)}</td>
          <td>${escHtml(u.name || '')}</td>
          <td>${escHtml(u.role)}</td>
          <td><span class="badge badge-${u.status === 'active' ? 'safe' : 'high'}">${u.status === 'active' ? '启用' : '禁用'}</span></td>
          <td>${escHtml(u.department || '-')}</td>
          <td>${u.last_login ? new Date(u.last_login).toLocaleString('zh-CN') : '-'}</td>
          <td>
            <button class="btn-icon" data-action="edit" data-id="${u.id}" title="编辑">✏️</button>
            <button class="btn-icon" data-action="toggle" data-id="${u.id}" title="切换状态">${u.status === 'active' ? '🔒' : '🔓'}</button>
            <button class="btn-icon" data-action="reset" data-id="${u.id}" title="重置密钥">🔑</button>
            <button class="btn-icon" data-action="delete" data-id="${u.id}" title="删除" ${u.role === 'super_admin' ? 'disabled' : ''}>🗑️</button>
          </td>
        </tr>
      `).join('');

      document.getElementById('admin-users-table').innerHTML = `
        <table class="admin-table">
          <thead>
            <tr>
              <th>工号</th><th>姓名</th><th>角色</th><th>状态</th><th>部门</th><th>最后登录</th><th>操作</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;

      // 分页
      const totalPages = Math.ceil(data.total / limit);
      document.getElementById('admin-pagination').innerHTML = totalPages > 1
        ? `<button ${currentSkip === 0 ? 'disabled' : ''} onclick="window.adminPrevPage()">上一页</button>
           <span>第 ${Math.floor(currentSkip / limit) + 1} / ${totalPages} 页</span>
           <button ${currentSkip + limit >= data.total ? 'disabled' : ''} onclick="window.adminNextPage()">下一页</button>`
        : '';

      window.adminPrevPage = () => { currentSkip = Math.max(0, currentSkip - limit); loadUsers(); };
      window.adminNextPage = () => { currentSkip += limit; loadUsers(); };
    }

    // 初始加载
    loadUsers();

    // 搜索和筛选
    document.getElementById('admin-search')?.addEventListener('input', () => { currentSkip = 0; loadUsers(); });
    document.getElementById('admin-role-filter')?.addEventListener('change', () => { currentSkip = 0; loadUsers(); });
    document.getElementById('admin-status-filter')?.addEventListener('change', () => { currentSkip = 0; loadUsers(); });

    // 新增用户
    document.getElementById('admin-add-btn')?.addEventListener('click', () => {
      document.getElementById('user-modal-title').textContent = '新增用户';
      document.getElementById('user-form').reset();
      document.getElementById('user-id').value = '';
      document.getElementById('user-employee-id').readOnly = false;
      document.getElementById('api-key-hint').textContent = '(必填，至少32字符)';
      document.getElementById('user-modal').style.display = 'flex';
    });

    // 表格操作
    document.getElementById('admin-users-table')?.addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;

      const action = btn.dataset.action;
      const id = btn.dataset.id;

      if (action === 'edit') {
        // 获取用户详情并填充表单
        const user = data.items.find(u => u.id == id);
        if (user) {
          document.getElementById('user-modal-title').textContent = '编辑用户';
          document.getElementById('user-id').value = user.id;
          document.getElementById('user-employee-id').value = user.employee_id;
          document.getElementById('user-employee-id').readOnly = true;
          document.getElementById('user-name').value = user.name || '';
          document.getElementById('user-api-key').value = '';
          document.getElementById('user-role').value = user.role;
          document.getElementById('user-department').value = user.department || '';
          document.getElementById('user-team').value = user.team || '';
          document.getElementById('user-group').value = user.group_name || '';
          document.getElementById('api-key-hint').textContent = '(留空则不修改)';
          document.getElementById('user-modal').style.display = 'flex';
        }
      } else if (action === 'toggle') {
        if (confirm('确定要切换该用户的状态吗？')) {
          await fetch(`${API_BASE}/api/admin/users/${id}/toggle-status`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
          });
          loadUsers();
        }
      } else if (action === 'reset') {
        const newKey = prompt('请输入新的 API 密钥（至少32字符）：');
        if (newKey && newKey.length >= 32) {
          await fetch(`${API_BASE}/api/admin/users/${id}/reset-key?new_key=${encodeURIComponent(newKey)}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
          });
          alert('密钥已重置');
        } else if (newKey) {
          alert('密钥长度不足32字符');
        }
      } else if (action === 'delete') {
        if (confirm('确定要删除该用户吗？此操作不可恢复。')) {
          await fetch(`${API_BASE}/api/admin/users/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
          });
          loadUsers();
        }
      }
    });

    // 表单提交
    document.getElementById('user-form')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const id = document.getElementById('user-id').value;
      const isEdit = !!id;

      const body = {
        employee_id: document.getElementById('user-employee-id').value,
        name: document.getElementById('user-name').value,
        role: document.getElementById('user-role').value,
        department: document.getElementById('user-department').value || null,
        team: document.getElementById('user-team').value || null,
        group_name: document.getElementById('user-group').value || null,
      };

      const apiKey = document.getElementById('user-api-key').value;
      if (apiKey) body.api_key = apiKey;

      if (!isEdit && !apiKey) {
        alert('新增用户必须提供 API 密钥');
        return;
      }

      const url = isEdit ? `${API_BASE}/api/admin/users/${id}` : `${API_BASE}/api/admin/users`;
      const method = isEdit ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(body)
      });

      const result = await res.json();
      if (res.ok) {
        closeUserModal();
        loadUsers();
      } else {
        alert(result.detail || '保存失败');
      }
    });

    // 导出
    document.getElementById('admin-export-btn')?.addEventListener('click', () => {
      const role = document.getElementById('admin-role-filter')?.value || '';
      const status = document.getElementById('admin-status-filter')?.value || '';
      let url = `${API_BASE}/api/admin/users/export?`;
      if (role) url += `role=${role}&`;
      if (status) url += `status=${status}&`;
      window.open(url, '_blank');
    });

    // 关闭弹窗
    window.closeUserModal = () => {
      document.getElementById('user-modal').style.display = 'none';
    };
  }
```

- [ ] **Step 4: Commit**

```bash
git add docs/assets/app.js
git commit -m "feat(frontend): add admin users management page

- Add admin/users route and page rendering
- Support search, filter by role/status
- Add/edit/delete users via modal form
- Toggle status and reset API key
- Export users to CSV

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 前端 - 添加登录日志页面

**Files:**
- Modify: `docs/assets/app.js`

- [ ] **Step 1: 添加登录日志页面渲染函数**

```javascript
  /* ===================== ADMIN LOGS PAGE ===================== */
  function renderAdminLogsPage() {
    return `
<div class="detail-page px-container max-w-7xl" style="padding-bottom:4rem">
  <div style="text-align:center;padding:2rem 0 1.5rem">
    <h1 style="font-size:2rem;font-weight:700;margin-bottom:.5rem">登录日志</h1>
    <p class="text-muted">查看用户登录历史和安全审计</p>
  </div>

  <div class="admin-toolbar" style="display:flex;gap:.75rem;flex-wrap:wrap;margin-bottom:1.5rem">
    <input type="text" id="logs-search" class="form-input" placeholder="搜索工号..." style="flex:1;min-width:200px">
    <select id="logs-status-filter" class="form-input" style="width:auto">
      <option value="">全部状态</option>
      <option value="success">成功</option>
      <option value="failed">失败</option>
    </select>
    <button class="btn-secondary" id="logs-refresh-btn">刷新</button>
  </div>

  <div id="logs-table" class="admin-table-wrapper" style="overflow-x:auto">
    <p class="text-muted">加载中...</p>
  </div>

  <div id="logs-pagination" class="pagination" style="margin-top:1rem"></div>
</div>`;
  }
```

- [ ] **Step 2: 添加登录日志页面事件绑定**

```javascript
  function bindAdminLogsEvents() {
    const API_BASE = window.location.hostname === 'localhost' ? 'http://localhost:8001' : '';
    let token = localStorage.getItem('access_token');
    let currentSkip = 0;
    const limit = 20;

    if (!token) {
      document.getElementById('logs-table').innerHTML = '<p class="text-muted">请先登录</p>';
      return;
    }

    function loadLogs() {
      const search = document.getElementById('logs-search')?.value || '';
      const status = document.getElementById('logs-status-filter')?.value || '';

      let url = `${API_BASE}/api/admin/login-logs?skip=${currentSkip}&limit=${limit}`;
      if (search) url += `&employee_id=${encodeURIComponent(search)}`;
      if (status) url += `&status=${status}`;

      fetch(url, { headers: { 'Authorization': `Bearer ${token}` } })
        .then(r => r.json())
        .then(data => {
          if (data.detail) {
            document.getElementById('logs-table').innerHTML = `<p class="text-muted">${escHtml(data.detail)}</p>`;
            return;
          }
          renderLogsTable(data);
        })
        .catch(() => {
          document.getElementById('logs-table').innerHTML = '<p class="text-muted">加载失败</p>';
        });
    }

    function renderLogsTable(data) {
      const rows = data.items.map(log => `
        <tr>
          <td>${escHtml(log.employee_id)}</td>
          <td><span class="badge badge-${log.status === 'success' ? 'safe' : 'high'}">${log.status === 'success' ? '成功' : '失败'}</span></td>
          <td>${log.login_time ? new Date(log.login_time).toLocaleString('zh-CN') : '-'}</td>
          <td>${escHtml(log.ip_address || '-')}</td>
          <td title="${escHtml(log.user_agent || '')}">${escHtml((log.user_agent || '').substring(0, 30))}${log.user_agent && log.user_agent.length > 30 ? '...' : ''}</td>
          <td>${escHtml(log.failure_reason || '-')}</td>
        </tr>
      `).join('');

      document.getElementById('logs-table').innerHTML = `
        <table class="admin-table">
          <thead>
            <tr>
              <th>工号</th><th>状态</th><th>登录时间</th><th>IP 地址</th><th>浏览器</th><th>失败原因</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;

      const totalPages = Math.ceil(data.total / limit);
      document.getElementById('logs-pagination').innerHTML = totalPages > 1
        ? `<button ${currentSkip === 0 ? 'disabled' : ''} onclick="window.logsPrevPage()">上一页</button>
           <span>第 ${Math.floor(currentSkip / limit) + 1} / ${totalPages} 页</span>
           <button ${currentSkip + limit >= data.total ? 'disabled' : ''} onclick="window.logsNextPage()">下一页</button>`
        : '';

      window.logsPrevPage = () => { currentSkip = Math.max(0, currentSkip - limit); loadLogs(); };
      window.logsNextPage = () => { currentSkip += limit; loadLogs(); };
    }

    loadLogs();

    document.getElementById('logs-search')?.addEventListener('input', () => { currentSkip = 0; loadLogs(); });
    document.getElementById('logs-status-filter')?.addEventListener('change', () => { currentSkip = 0; loadLogs(); });
    document.getElementById('logs-refresh-btn')?.addEventListener('click', loadLogs);
  }
```

- [ ] **Step 3: Commit**

```bash
git add docs/assets/app.js
git commit -m "feat(frontend): add login logs admin page

- Display login history with filters
- Show employee_id, status, time, IP, user_agent
- Pagination support

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: 添加管理后台 CSS 样式

**Files:**
- Modify: `docs/assets/style.css` (或对应的样式文件)

- [ ] **Step 1: 添加管理后台相关样式**

```css
/* Admin Table */
.admin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: .875rem;
}
.admin-table th, .admin-table td {
  padding: .75rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
}
.admin-table th {
  font-weight: 600;
  background: var(--muted);
}
.admin-table tr:hover {
  background: var(--muted);
}

/* Modal */
.modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,.5);
}
.modal-content {
  position: relative;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 1.5rem;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}
.modal-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: var(--muted-foreground);
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: .75rem;
  margin-top: 1.5rem;
}

/* Buttons */
.btn-primary {
  background: var(--accent);
  color: var(--accent-foreground);
  padding: .5rem 1rem;
  border-radius: var(--radius);
  border: none;
  cursor: pointer;
  font-weight: 500;
}
.btn-secondary {
  background: var(--muted);
  color: var(--foreground);
  padding: .5rem 1rem;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  cursor: pointer;
}
.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  padding: .25rem;
  font-size: 1rem;
}
.btn-icon:disabled {
  opacity: .5;
  cursor: not-allowed;
}

/* Form */
.form-input {
  width: 100%;
  padding: .5rem .75rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--background);
  color: var(--foreground);
  font-size: .875rem;
}
.form-group {
  margin-bottom: 1rem;
}
.form-label {
  display: block;
  font-weight: 500;
  margin-bottom: .25rem;
  font-size: .875rem;
}
```

- [ ] **Step 2: Commit**

```bash
git add docs/assets/style.css
git commit -m "style: add admin page styles

- Admin table with hover effect
- Modal dialog styling
- Form input and button styles

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 验收标准

- [ ] 登录限流正常工作（5次失败后锁定30分钟）
- [ ] 用户导出 CSV 功能正常
- [ ] 用户导入 CSV 功能正常（支持 skip/overwrite/raise 策略）
- [ ] 前端管理后台可访问（#admin/users, #admin/logs）
- [ ] 用户 CRUD 操作正常
- [ ] 登录日志查询正常

---

**P2 增强功能完成。用户管理模块全部实现。**
