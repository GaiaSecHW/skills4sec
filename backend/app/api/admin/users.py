from fastapi import APIRouter, HTTPException, status, Depends, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from typing import Optional, List
from datetime import datetime
import secrets
import csv
import io

from app.models.user import User
from app.models.login_log import LoginLog
from app.models.admin_log import AdminLog
from app.schemas.user import (
    UserCreateByAdmin, UserUpdateByAdmin, UserOutNew
)
from app.schemas.log import LoginLogOut, AdminLogOut
from app.utils.security import (
    get_password_hash,
    get_current_admin_user,
    get_current_superuser,
    validate_api_key_complexity,
)
from app.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])


# ============ 辅助函数 ============

async def log_admin_action(
    request: Request,
    admin: User,
    action: str,
    target_user: Optional[User] = None,
    details: Optional[dict] = None
):
    """记录管理员操作日志"""
    client_ip = request.client.host if request.client else None
    await AdminLog.create(
        admin_id=admin.id,
        admin_employee_id=admin.employee_id,
        action=action,
        target_user_id=target_user.id if target_user else None,
        target_employee_id=target_user.employee_id if target_user else None,
        details=details,
        ip_address=client_ip,
    )


def generate_api_key() -> str:
    """生成安全的 API 密钥"""
    return secrets.token_urlsafe(32)


# ============ 用户列表和创建 ============

@router.get("/users", response_model=dict)
async def list_users(
    request: Request,
    skip: int = Query(0, ge=0, description="偏移量"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    role: Optional[str] = Query(None, description="角色筛选"),
    status: Optional[str] = Query(None, description="状态筛选"),
    department: Optional[str] = Query(None, description="部门筛选"),
    keyword: Optional[str] = Query(None, description="关键词搜索(工号/姓名)"),
    admin: User = Depends(get_current_admin_user)
):
    """获取用户列表 (管理员) - 支持分页、筛选和关键词搜索"""
    query = User.all()

    if role:
        query = query.filter(role=role)
    if status:
        query = query.filter(status=status)
    if department:
        query = query.filter(department=department)
    if keyword:
        query = query.filter(employee_id__icontains=keyword) | User.filter(name__icontains=keyword)

    total = await query.count()
    users = await query.offset(skip).limit(limit).order_by("-created_at")

    return {
        "success": True,
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": [UserOutNew.model_validate(u) for u in users]
    }


@router.post("/users", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    user_data: UserCreateByAdmin,
    admin: User = Depends(get_current_admin_user)
):
    """创建用户 (管理员)"""
    if await User.exists(employee_id=user_data.employee_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="工号已存在")

    is_valid, msg = validate_api_key_complexity(user_data.api_key)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"API密钥不符合要求: {msg}")

    if user_data.role in ("admin", "super_admin") and admin.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有超级管理员可以创建管理员账户")

    user = await User.create(
        employee_id=user_data.employee_id,
        name=user_data.name,
        api_key_hash=get_password_hash(user_data.api_key),
        role=user_data.role,
        status="active",
        is_active=True,
        is_superuser=(user_data.role == "super_admin"),
        department=user_data.department,
        team=user_data.team,
        group_name=user_data.group_name,
    )

    await log_admin_action(request=request, admin=admin, action="create_user", target_user=user,
                           details={"role": user_data.role, "department": user_data.department})

    return {"success": True, "message": "用户创建成功", "data": UserOutNew.model_validate(user)}


# ============ CSV 导入导出 (必须在 /users/{user_id} 之前) ============

@router.get("/users/export")
async def export_users_csv(
    request: Request,
    role: Optional[str] = Query(None, description="角色筛选"),
    status_filter: Optional[str] = Query(None, alias="status", description="状态筛选"),
    department: Optional[str] = Query(None, description="部门筛选"),
    admin: User = Depends(get_current_admin_user)
):
    """导出用户为 CSV 文件 (管理员)"""
    query = User.all()

    if role:
        query = query.filter(role=role)
    if status_filter:
        query = query.filter(status=status_filter)
    if department:
        query = query.filter(department=department)

    users = await query.order_by("employee_id")

    output = io.StringIO()
    output.write('\ufeff')  # UTF-8 BOM for Excel
    writer = csv.writer(output)

    writer.writerow(["工号", "姓名", "角色", "状态", "部门", "团队", "分组", "技能数", "最后登录", "创建时间"])

    for user in users:
        writer.writerow([
            user.employee_id, user.name or "", user.role, user.status,
            user.department or "", user.team or "", user.group_name or "",
            user.skills_count,
            user.last_login.isoformat() if user.last_login else "",
            user.created_at.isoformat() if user.created_at else ""
        ])

    await log_admin_action(request=request, admin=admin, action="export_users",
                           details={"count": len(users)})

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )


@router.post("/users/import", response_model=dict)
async def import_users_csv(
    request: Request,
    file: UploadFile = File(..., description="CSV 文件"),
    generate_key: bool = Query(False, description="是否自动生成 API 密钥"),
    admin: User = Depends(get_current_superuser)
):
    """从 CSV 批量导入用户 (仅超级管理员)"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只支持 CSV 文件")

    content = await file.read()
    if content.startswith(b'\xef\xbb\xbf'):
        content = content[3:]

    try:
        text_content = content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text_content = content.decode('gbk')
        except UnicodeDecodeError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法解码文件，请使用 UTF-8 或 GBK 编码")

    reader = csv.reader(io.StringIO(text_content))
    rows = list(reader)

    if len(rows) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV 文件为空或只有表头")

    data_rows = rows[1:]
    created, failed, new_keys = [], [], []

    for row in data_rows:
        if not row or not row[0].strip():
            continue

        try:
            employee_id = row[0].strip()
            name = row[1].strip() if len(row) > 1 else employee_id
            role = row[2].strip() if len(row) > 2 and row[2].strip() else "user"
            department = row[3].strip() if len(row) > 3 else None
            team = row[4].strip() if len(row) > 4 else None
            group_name = row[5].strip() if len(row) > 5 else None
            api_key = row[6].strip() if len(row) > 6 else None

            if role not in ("user", "admin", "super_admin"):
                failed.append({"employee_id": employee_id, "reason": f"无效角色: {role}"})
                continue

            if await User.exists(employee_id=employee_id):
                failed.append({"employee_id": employee_id, "reason": "工号已存在"})
                continue

            if not api_key:
                if generate_key:
                    api_key = generate_api_key()
                    new_keys.append({"employee_id": employee_id, "api_key": api_key})
                else:
                    failed.append({"employee_id": employee_id, "reason": "缺少 API 密钥"})
                    continue
            else:
                is_valid, msg = validate_api_key_complexity(api_key)
                if not is_valid:
                    failed.append({"employee_id": employee_id, "reason": f"API密钥不符合要求: {msg}"})
                    continue

            user = await User.create(
                employee_id=employee_id, name=name, api_key_hash=get_password_hash(api_key),
                role=role, status="active", is_active=True, is_superuser=(role == "super_admin"),
                department=department, team=team, group_name=group_name,
            )
            created.append(UserOutNew.model_validate(user))

        except Exception as e:
            failed.append({"employee_id": row[0] if row else "unknown", "reason": str(e)})

    await log_admin_action(request=request, admin=admin, action="import_users",
                           details={"total": len(data_rows), "created": len(created), "failed": len(failed)})

    return {
        "success": True,
        "message": f"成功导入 {len(created)} 个用户，{len(failed)} 个失败",
        "data": {"created": created, "failed": failed, "generated_keys": new_keys if generate_key else []}
    }


@router.post("/users/batch", response_model=dict)
async def batch_create_users(
    request: Request,
    users_data: List[UserCreateByAdmin],
    admin: User = Depends(get_current_superuser)
):
    """批量创建用户 (仅超级管理员) - 最多一次创建 100 个用户"""
    if len(users_data) > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="单次最多创建 100 个用户")

    created, failed = [], []

    for user_data in users_data:
        try:
            if await User.exists(employee_id=user_data.employee_id):
                failed.append({"employee_id": user_data.employee_id, "reason": "工号已存在"})
                continue

            is_valid, msg = validate_api_key_complexity(user_data.api_key)
            if not is_valid:
                failed.append({"employee_id": user_data.employee_id, "reason": f"API密钥不符合要求: {msg}"})
                continue

            user = await User.create(
                employee_id=user_data.employee_id, name=user_data.name,
                api_key_hash=get_password_hash(user_data.api_key), role=user_data.role,
                status="active", is_active=True, is_superuser=(user_data.role == "super_admin"),
                department=user_data.department, team=user_data.team, group_name=user_data.group_name,
            )
            created.append(UserOutNew.model_validate(user))

        except Exception as e:
            failed.append({"employee_id": user_data.employee_id, "reason": str(e)})

    await log_admin_action(request=request, admin=admin, action="batch_create_users",
                           details={"total": len(users_data), "created": len(created), "failed": len(failed)})

    return {
        "success": True,
        "message": f"成功创建 {len(created)} 个用户，{len(failed)} 个失败",
        "data": {"created": created, "failed": failed}
    }


# ============ 单个用户操作 ============

@router.get("/users/{user_id}", response_model=dict)
async def get_user(user_id: int, admin: User = Depends(get_current_admin_user)):
    """获取用户详情 (管理员)"""
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"success": True, "data": UserOutNew.model_validate(user)}


@router.put("/users/{user_id}", response_model=dict)
async def update_user(
    request: Request,
    user_id: int,
    update_data: UserUpdateByAdmin,
    admin: User = Depends(get_current_admin_user)
):
    """更新用户信息 (管理员)"""
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.role in ("admin", "super_admin") and admin.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有超级管理员可以修改管理员账户")

    if user.id == admin.id and update_data.role and update_data.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能降低自己的角色等级")

    changes = {}

    if update_data.name is not None:
        changes["name"] = {"old": user.name, "new": update_data.name}
        user.name = update_data.name

    if update_data.api_key is not None:
        is_valid, msg = validate_api_key_complexity(update_data.api_key)
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"API密钥不符合要求: {msg}")
        changes["api_key"] = "updated"
        user.api_key_hash = get_password_hash(update_data.api_key)

    if update_data.role is not None:
        if update_data.role in ("admin", "super_admin") and admin.role != "super_admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有超级管理员可以设置管理员角色")
        changes["role"] = {"old": user.role, "new": update_data.role}
        user.role = update_data.role
        user.is_superuser = (update_data.role == "super_admin")

    if update_data.status is not None:
        changes["status"] = {"old": user.status, "new": update_data.status}
        user.status = update_data.status
        user.is_active = (update_data.status == "active")

    if update_data.department is not None:
        changes["department"] = {"old": user.department, "new": update_data.department}
        user.department = update_data.department

    if update_data.team is not None:
        changes["team"] = {"old": user.team, "new": update_data.team}
        user.team = update_data.team

    if update_data.group_name is not None:
        changes["group_name"] = {"old": user.group_name, "new": update_data.group_name}
        user.group_name = update_data.group_name

    await user.save()
    await log_admin_action(request=request, admin=admin, action="update_user", target_user=user, details={"changes": changes})

    return {"success": True, "message": "用户信息更新成功", "data": UserOutNew.model_validate(user)}


@router.delete("/users/{user_id}", response_model=dict)
async def delete_user(request: Request, user_id: int, admin: User = Depends(get_current_admin_user)):
    """删除用户 (管理员) - 不能删除超级管理员"""
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除自己的账户")

    if user.role in ("admin", "super_admin") and admin.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有超级管理员可以删除管理员账户")

    if user.role == "super_admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除超级管理员")

    await log_admin_action(request=request, admin=admin, action="delete_user", target_user=user,
                           details={"deleted_employee_id": user.employee_id, "deleted_name": user.name})

    await user.delete()
    return {"success": True, "message": "用户删除成功"}


@router.post("/users/{user_id}/reset-key", response_model=dict)
async def reset_user_api_key(request: Request, user_id: int, admin: User = Depends(get_current_admin_user)):
    """重置用户 API 密钥 (管理员)"""
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.role in ("admin", "super_admin") and admin.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有超级管理员可以重置管理员的API密钥")

    new_api_key = generate_api_key()
    user.api_key_hash = get_password_hash(new_api_key)
    await user.save()

    await log_admin_action(request=request, admin=admin, action="reset_api_key", target_user=user)

    return {"success": True, "message": "API密钥已重置", "data": {"employee_id": user.employee_id, "new_api_key": new_api_key}}


@router.post("/users/{user_id}/toggle-status", response_model=dict)
async def toggle_user_status(request: Request, user_id: int, admin: User = Depends(get_current_admin_user)):
    """切换用户状态 (管理员) - 在 active 和 disabled 之间切换"""
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用自己的账户")

    if user.role in ("admin", "super_admin") and admin.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有超级管理员可以切换管理员状态")

    if user.role == "super_admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用超级管理员")

    old_status = user.status
    if user.status == "active":
        user.status = "disabled"
        user.is_active = False
    else:
        user.status = "active"
        user.is_active = True

    await user.save()
    await log_admin_action(request=request, admin=admin, action="toggle_status", target_user=user,
                           details={"old_status": old_status, "new_status": user.status})

    return {"success": True, "message": f"用户状态已切换为 {user.status}", "data": UserOutNew.model_validate(user)}


# ============ 日志查询接口 ============

@router.get("/login-logs", response_model=dict)
async def list_login_logs(
    skip: int = Query(0, ge=0, description="偏移量"),
    limit: int = Query(50, ge=1, le=200, description="每页数量"),
    employee_id: Optional[str] = Query(None, description="工号筛选"),
    status: Optional[str] = Query(None, description="状态筛选(success/failed)"),
    start_date: Optional[datetime] = Query(None, description="开始时间"),
    end_date: Optional[datetime] = Query(None, description="结束时间"),
    admin: User = Depends(get_current_admin_user)
):
    """查询登录日志 (管理员)"""
    query = LoginLog.all()

    if employee_id:
        query = query.filter(employee_id__icontains=employee_id)
    if status:
        query = query.filter(status=status)
    if start_date:
        query = query.filter(login_time__gte=start_date)
    if end_date:
        query = query.filter(login_time__lte=end_date)

    total = await query.count()
    logs = await query.offset(skip).limit(limit).order_by("-login_time")

    return {"success": True, "total": total, "skip": skip, "limit": limit,
            "data": [LoginLogOut.model_validate(log) for log in logs]}


@router.get("/admin-logs", response_model=dict)
async def list_admin_logs(
    skip: int = Query(0, ge=0, description="偏移量"),
    limit: int = Query(50, ge=1, le=200, description="每页数量"),
    admin_employee_id: Optional[str] = Query(None, description="管理员工号"),
    action: Optional[str] = Query(None, description="操作类型"),
    target_employee_id: Optional[str] = Query(None, description="目标用户工号"),
    start_date: Optional[datetime] = Query(None, description="开始时间"),
    end_date: Optional[datetime] = Query(None, description="结束时间"),
    admin: User = Depends(get_current_superuser)
):
    """查询管理员操作日志 (仅超级管理员)"""
    query = AdminLog.all()

    if admin_employee_id:
        query = query.filter(admin_employee_id__icontains=admin_employee_id)
    if action:
        query = query.filter(action__icontains=action)
    if target_employee_id:
        query = query.filter(target_employee_id__icontains=target_employee_id)
    if start_date:
        query = query.filter(created_at__gte=start_date)
    if end_date:
        query = query.filter(created_at__lte=end_date)

    total = await query.count()
    logs = await query.offset(skip).limit(limit).order_by("-created_at")

    return {"success": True, "total": total, "skip": skip, "limit": limit,
            "data": [AdminLogOut.model_validate(log) for log in logs]}
