"""错误码定义

格式: {模块}-{HTTP状态码}-{序号}
示例: AUTH-401-01, SUBM-500-01
"""
from typing import Tuple, Optional


class ErrorCode:
    """错误码定义"""

    # ========== AUTH 认证模块 ==========
    AUTH_401_01 = ("AUTH-401-01", "Token 已过期", "请重新登录")
    AUTH_401_02 = ("AUTH-401-02", "Token 无效", "Token 格式错误或被篡改")
    AUTH_401_03 = ("AUTH-401-03", "API Key 无效", "请检查 API Key 是否正确")
    AUTH_401_04 = ("AUTH-401-04", "登录已过期", "请重新登录")
    AUTH_403_01 = ("AUTH-403-01", "权限不足", "需要管理员权限")
    AUTH_403_02 = ("AUTH-403-02", "访问被拒绝", "您没有权限访问此资源")
    AUTH_429_01 = ("AUTH-429-01", "登录失败次数过多", "账户已锁定 30 分钟")

    # ========== USER 用户模块 ==========
    USER_404_01 = ("USER-404-01", "用户不存在", "请检查工号是否正确")
    USER_404_02 = ("USER-404-02", "用户已禁用", "请联系管理员")
    USER_409_01 = ("USER-409-01", "工号已存在", "该工号已被注册")
    USER_409_02 = ("USER-409-02", "邮箱已注册", "该邮箱已被使用")
    USER_400_01 = ("USER-400-01", "API Key 格式错误", "长度需至少 6 位")
    USER_400_02 = ("USER-400-02", "工号格式错误", "工号格式不正确")

    # ========== SUBM 技能提交模块 ==========
    SUBM_400_01 = ("SUBM-400-01", "提交参数不完整", "缺少必填字段")
    SUBM_400_02 = ("SUBM-400-02", "提交参数无效", "请检查参数格式")
    SUBM_404_01 = ("SUBM-404-01", "提交记录不存在", "submission_id 无效")
    SUBM_409_01 = ("SUBM-409-01", "重复提交", "该技能已提交过")
    SUBM_409_02 = ("SUBM-409-02", "提交状态不允许", "当前状态不允许此操作")
    SUBM_500_01 = ("SUBM-500-01", "Issue 创建失败", "Gitea API 返回错误")
    SUBM_500_02 = ("SUBM-500-02", "提交处理失败", "服务器内部错误")

    # ========== SKILL 技能模块 ==========
    SKILL_404_01 = ("SKILL-404-01", "技能不存在", "技能 ID 无效")
    SKILL_409_01 = ("SKILL-409-01", "技能已存在", "同名技能已存在")
    SKILL_400_01 = ("SKILL-400-01", "技能参数错误", "请检查技能配置")

    # ========== SYNC 同步模块 ==========
    SYNC_503_01 = ("SYNC-503-01", "Gitea API 超时", "服务无响应，请稍后重试")
    SYNC_502_01 = ("SYNC-502-01", "Gitea API 错误", "上游服务返回异常")
    SYNC_401_01 = ("SYNC-401-01", "Gitea Token 无效", "请检查配置")
    SYNC_404_01 = ("SYNC-404-01", "Gitea 仓库不存在", "请检查仓库地址")

    # ========== ADMIN 管理模块 ==========
    ADMIN_403_01 = ("ADMIN-403-01", "需要管理员权限", "此操作需要管理员权限")
    ADMIN_403_02 = ("ADMIN-403-02", "需要超级管理员权限", "此操作需要超级管理员权限")

    # ========== SYS 系统模块 ==========
    SYS_500_01 = ("SYS-500-01", "数据库连接失败", "请检查数据库状态")
    SYS_500_02 = ("SYS-500-02", "内部服务错误", "请联系管理员")
    SYS_500_03 = ("SYS-500-03", "缓存服务错误", "请稍后重试")
    SYS_503_01 = ("SYS-503-01", "服务暂不可用", "服务正在维护中")

    @classmethod
    def get(cls, code: str) -> Tuple[str, str, str]:
        """
        获取错误码详情

        Args:
            code: 错误码字符串，如 "AUTH-401-01"

        Returns:
            (code, message, suggestion) 元组
        """
        # 使用 getattr 查找类属性
        attr_name = code.replace("-", "_").replace(" ", "_")
        result = getattr(cls, attr_name, None)

        if result:
            return result

        # 未找到，返回默认值
        return (code, "未知错误", "请联系管理员")

    @classmethod
    def get_message(cls, code: str) -> str:
        """获取错误消息"""
        return cls.get(code)[1]

    @classmethod
    def get_suggestion(cls, code: str) -> str:
        """获取解决建议"""
        return cls.get(code)[2]