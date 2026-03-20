# backend/app/models/admin_log.py
from tortoise import fields
from tortoise.models import Model


class AdminLog(Model):
    """管理员操作日志模型"""
    id = fields.IntField(pk=True)
    admin_id = fields.IntField(index=True, description="操作者用户ID")
    admin_employee_id = fields.CharField(max_length=20, description="操作者工号")
    action = fields.CharField(max_length=50, description="操作类型: reset_key/delete_user/toggle_status等")
    target_user_id = fields.IntField(null=True, description="目标用户ID")
    target_employee_id = fields.CharField(max_length=20, null=True, description="目标用户工号")
    details = fields.JSONField(null=True, description="操作详情")
    ip_address = fields.CharField(max_length=45, null=True, description="IP地址")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "admin_logs"
        indexes = [
            ("admin_id",),
            ("action",),
            ("created_at",),
        ]

    def __str__(self):
        return f"{self.admin_employee_id} - {self.action}"
