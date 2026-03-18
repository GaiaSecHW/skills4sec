from tortoise import fields
from tortoise.models import Model


class User(Model):
    """用户模型"""
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=64, unique=True, index=True)
    email = fields.CharField(max_length=128, unique=True, index=True)
    hashed_password = fields.CharField(max_length=255)
    is_active = fields.BooleanField(default=True)
    is_superuser = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"

    def __str__(self):
        return self.username


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
