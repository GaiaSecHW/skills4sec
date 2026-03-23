# backend/app/core/harness_logging/audit.py
"""审计日志记录器"""
from typing import Dict, Optional, Any
from datetime import datetime
from app.core.harness_logging.logger import HarnessLogger, trace_id_ctx, actor_ctx


# 需要写入数据库的审计动作
_DB_AUDIT_ACTIONS = {
    "user_login",
    "user_logout",
    "user_created",
    "user_updated",
    "user_deleted",
    "skill_approved",
    "skill_rejected",
    "submission_created",
    "submission_updated",
}


class AuditLogger:
    """
    审计日志记录器

    使用双轨策略：
    - 文件：logs/audit.log（90天保留）
    - 数据库：AuditLog 表（可选）

    使用场景：
    - 用户登录/登出 → 同时写入两者
    - 数据变更操作 → 同时写入两者
    - 内部系统操作 → 仅写入文件
    """

    def __init__(self, module: str = "audit"):
        self.file_logger = HarnessLogger(module)
        self._db_model = None  # 延迟导入

    def _get_db_model(self):
        """延迟获取数据库模型"""
        if self._db_model is None:
            try:
                from app.models.audit import AuditLog
                self._db_model = AuditLog
            except ImportError:
                pass
        return self._db_model

    def _should_persist_to_db(self, action: str) -> bool:
        """检查是否需要写入数据库"""
        return action in _DB_AUDIT_ACTIONS

    async def _persist_to_db(
        self,
        action: str,
        actor: Dict[str, Any],
        target: Dict[str, Any],
        result: str,
        details: Optional[Dict] = None,
    ) -> None:
        """写入数据库"""
        AuditLog = self._get_db_model()
        if AuditLog is None:
            return

        try:
            await AuditLog.create(
                action=action,
                actor_id=actor.get("employee_id"),
                actor_name=actor.get("name"),
                target_type=target.get("type"),
                target_id=target.get("id"),
                result=result,
                details=details,
                ip_address=actor.get("ip"),
            )
        except Exception as e:
            # 数据库写入失败不影响审计（已有文件日志）
            self.file_logger.warning(
                "audit_db_write_failed",
                event="audit_db_write_failed",
                error=str(e),
                action=action,
            )

    def log(
        self,
        action: str,
        actor: Dict[str, Any],
        target: Dict[str, Any],
        result: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录审计日志"""
        trace_id = trace_id_ctx.get()
        if trace_id:
            details = details or {}
            details["trace_id"] = trace_id

        self.file_logger.info(
            f"Audit: {action}",
            event=f"audit_{action}",
            actor=actor,
            target=target,
            result=result,
            details=details,
        )

    async def log_async(
        self,
        action: str,
        actor: Dict[str, Any],
        target: Dict[str, Any],
        result: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """异步记录审计日志（包含数据库写入）"""
        trace_id = trace_id_ctx.get()
        if trace_id:
            details = details or {}
            details["trace_id"] = trace_id

        self.file_logger.info(
            f"Audit: {action}",
            event=f"audit_{action}",
            actor=actor,
            target=target,
            result=result,
            details=details,
        )

        if self._should_persist_to_db(action):
            await self._persist_to_db(action, actor, target, result, details)

    def user_login(
        self,
        employee_id: str,
        name: str,
        ip: str,
        method: str = "api_key",
        success: bool = True,
    ) -> None:
        """用户登录审计"""
        self.log(
            action="user_login",
            actor={"employee_id": employee_id, "name": name, "ip": ip},
            target={"type": "user", "id": employee_id},
            result="success" if success else "failed",
            details={"method": method},
        )

    def user_logout(
        self,
        employee_id: str,
        name: str,
        ip: str,
    ) -> None:
        """用户登出审计"""
        self.log(
            action="user_logout",
            actor={"employee_id": employee_id, "name": name, "ip": ip},
            target={"type": "user", "id": employee_id},
            result="success",
        )

    def skill_approved(
        self,
        admin_employee_id: str,
        admin_name: str,
        submission_id: str,
        skill_name: str,
        issue_number: int,
    ) -> None:
        """技能审批通过审计"""
        self.log(
            action="skill_approved",
            actor={"employee_id": admin_employee_id, "name": admin_name},
            target={"type": "submission", "id": submission_id},
            result="success",
            details={"skill_name": skill_name, "issue_number": issue_number},
        )

    def skill_rejected(
        self,
        admin_employee_id: str,
        admin_name: str,
        submission_id: str,
        reason: str,
    ) -> None:
        """技能审批拒绝审计"""
        self.log(
            action="skill_rejected",
            actor={"employee_id": admin_employee_id, "name": admin_name},
            target={"type": "submission", "id": submission_id},
            result="success",
            details={"reason": reason},
        )
