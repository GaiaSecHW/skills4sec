# backend/tests/test_error_codes.py
"""错误码测试"""
import pytest
from app.core.harness_logging.error_codes import ErrorCode


class TestErrorCode:
    """错误码测试"""

    def test_error_code_format(self):
        """测试错误码格式"""
        code, message, suggestion = ErrorCode.AUTH_401_01
        assert code == "AUTH-401-01"
        assert message == "Token 已过期"
        assert suggestion == "请重新登录"

    def test_get_existing_code(self):
        """测试获取已定义的错误码"""
        result = ErrorCode.get("AUTH-401-01")
        assert result == ("AUTH-401-01", "Token 已过期", "请重新登录")

    def test_get_nonexistent_code(self):
        """测试获取未定义的错误码"""
        result = ErrorCode.get("UNKNOWN-999-99")
        assert result == ("UNKNOWN-999-99", "未知错误", "请联系管理员")

    def test_get_message(self):
        """测试获取错误消息"""
        assert ErrorCode.get_message("USER-404-01") == "用户不存在"

    def test_get_suggestion(self):
        """测试获取解决建议"""
        assert ErrorCode.get_suggestion("AUTH-401-01") == "请重新登录"

    def test_all_auth_codes(self):
        """测试所有认证错误码"""
        assert ErrorCode.AUTH_401_01 == ("AUTH-401-01", "Token 已过期", "请重新登录")
        assert ErrorCode.AUTH_401_02 == ("AUTH-401-02", "Token 无效", "Token 格式错误或被篡改")
        assert ErrorCode.AUTH_401_03 == ("AUTH-401-03", "API Key 无效", "请检查 API Key 是否正确")
        assert ErrorCode.AUTH_403_01 == ("AUTH-403-01", "权限不足", "需要管理员权限")
        assert ErrorCode.AUTH_429_01 == ("AUTH-429-01", "登录失败次数过多", "账户已锁定 30 分钟")

    def test_all_user_codes(self):
        """测试所有用户错误码"""
        assert ErrorCode.USER_404_01 == ("USER-404-01", "用户不存在", "请检查工号是否正确")
        assert ErrorCode.USER_409_01 == ("USER-409-01", "工号已存在", "该工号已被注册")

    def test_all_subm_codes(self):
        """测试所有提交错误码"""
        assert ErrorCode.SUBM_400_01 == ("SUBM-400-01", "提交参数不完整", "缺少必填字段")
        assert ErrorCode.SUBM_404_01 == ("SUBM-404-01", "提交记录不存在", "submission_id 无效")
        assert ErrorCode.SUBM_409_01 == ("SUBM-409-01", "重复提交", "该技能已提交过")
        assert ErrorCode.SUBM_500_01 == ("SUBM-500-01", "Issue 创建失败", "Gitea API 返回错误")

    def test_all_sync_codes(self):
        """测试所有同步错误码"""
        assert ErrorCode.SYNC_503_01 == ("SYNC-503-01", "Gitea API 超时", "服务无响应，请稍后重试")
        assert ErrorCode.SYNC_401_01 == ("SYNC-401-01", "Gitea Token 无效", "请检查配置")

    def test_all_sys_codes(self):
        """测试所有系统错误码"""
        assert ErrorCode.SYS_500_01 == ("SYS-500-01", "数据库连接失败", "请检查数据库状态")
        assert ErrorCode.SYS_500_02 == ("SYS-500-02", "内部服务错误", "请联系管理员")
