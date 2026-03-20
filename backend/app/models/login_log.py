# backend/app/models/login_log.py
from tortoise import fields
from tortoise.models import Model


class LoginLog(Model):
    """登录日志模型"""
    id = fields.IntField(pk=True)
    employee_id = fields.CharField(max_length=20, index=True, description="工号")
    login_time = fields.DatetimeField(auto_now_add=True)
    status = fields.CharField(max_length=20, description="状态: success/failed")
    ip_address = fields.CharField(max_length=45, null=True, description="IP地址")
    user_agent = fields.CharField(max_length=500, null=True, description="浏览器信息")
    device_id = fields.CharField(max_length=100, null=True, description="设备标识")
    failure_reason = fields.CharField(max_length=100, null=True, description="失败原因")

    class Meta:
        table = "login_logs"
        indexes = [
            ("employee_id",),
            ("login_time",),
            ("status",),
        ]

    def __str__(self):
        return f"{self.employee_id} - {self.status} at {self.login_time}"
