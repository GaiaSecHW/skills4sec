from tortoise import fields
from tortoise.models import Model


class User(Model):
    """用户模型 - 基于工号+API密钥认证"""
    id = fields.IntField(pk=True)
    # 保留旧字段向后兼容
    username = fields.CharField(max_length=64, unique=True, index=True, null=True)
    email = fields.CharField(max_length=128, unique=True, index=True, null=True)
    hashed_password = fields.CharField(max_length=255, null=True)
    # 新增字段
    employee_id = fields.CharField(max_length=20, unique=True, index=True, description="工号")
    api_key_hash = fields.CharField(max_length=255, null=True, description="API密钥(bcrypt哈希)")
    name = fields.CharField(max_length=100, null=True, description="姓名")
    role = fields.CharField(max_length=20, default="user", description="角色: super_admin/admin/user")
    status = fields.CharField(max_length=20, default="active", description="状态: active/disabled")
    department = fields.CharField(max_length=100, null=True, description="部门")
    team = fields.CharField(max_length=100, null=True, description="团队")
    group_name = fields.CharField(max_length=100, null=True, description="分组")
    skills_count = fields.IntField(default=0, description="上传技能数")
    # 保留现有字段
    is_active = fields.BooleanField(default=True)
    is_superuser = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    last_login = fields.DatetimeField(null=True, description="最后登录时间")

    class Meta:
        table = "users"
        indexes = [
            ("employee_id",),
            ("status", "role"),
        ]

    def __str__(self):
        return f"{self.employee_id} - {self.name}"


class Role(Model):
    """角色模型"""
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=64, unique=True)
    description = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "roles"


class UserRole(Model):
    """用户-角色关联"""
    user = fields.ForeignKeyField("models.User", related_name="user_roles")
    role = fields.ForeignKeyField("models.Role", related_name="role_users")

    class Meta:
        table = "user_roles"
        unique_together = ("user", "role")
