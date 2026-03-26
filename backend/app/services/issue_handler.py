"""
Gitea Issue 处理服务

负责轮询和处理 Gitea Issue 提交
"""
import re
from typing import Optional, List, Dict, Any
from datetime import datetime

import httpx
from app.core import get_logger
from app.config import settings

logger = get_logger("issue_handler")


class GiteaIssueHandler:
    """Gitea Issue 处理器"""

    def __init__(self):
        self.api_url = settings.GITEA_API_URL
        self.token = settings.GITEA_TOKEN
        self.repo = settings.GITEA_REPO

    def _get_headers(self) -> dict:
        """获取 API 请求头"""
        return {
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json",
        }

    async def list_unprocessed_issues(self, labels: List[str] = None) -> List[Dict[str, Any]]:
        """
        列出未处理的 Issue

        Args:
            labels: 过滤标签列表

        Returns:
            Issue 列表
        """
        if labels is None:
            labels = ["submission"]

        try:
            owner, repo = self.repo.split("/")
            url = f"{self.api_url}/repos/{owner}/{repo}/issues"

            params = {
                "state": "open",
                "labels": ",".join(labels),
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                issues = response.json()

            logger.info(f"Found {len(issues)} unprocessed issues")
            return issues

        except Exception as e:
            logger.error(f"Failed to list issues: {e}")
            return []

    async def get_issue(self, issue_number: int) -> Optional[Dict[str, Any]]:
        """获取单个 Issue 详情"""
        try:
            owner, repo = self.repo.split("/")
            url = f"{self.api_url}/repos/{owner}/{repo}/issues/{issue_number}"

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    timeout=30,
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error(f"Failed to get issue #{issue_number}: {e}")
            return None

    async def create_comment(self, issue_number: int, body: str) -> bool:
        """创建 Issue 评论"""
        try:
            owner, repo = self.repo.split("/")
            url = f"{self.api_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json={"body": body},
                    timeout=30,
                )
                response.raise_for_status()
                logger.info(f"Created comment on issue #{issue_number}")
                return True

        except Exception as e:
            logger.error(f"Failed to create comment: {e}")
            return False

    async def add_label(self, issue_number: int, label_name: str) -> bool:
        """添加标签到 Issue"""
        try:
            owner, repo = self.repo.split("/")
            url = f"{self.api_url}/repos/{owner}/{repo}/issues/{issue_number}/labels"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json={"labels": [label_name]},
                    timeout=30,
                )
                response.raise_for_status()
                logger.info(f"Added label '{label_name}' to issue #{issue_number}")
                return True

        except Exception as e:
            logger.error(f"Failed to add label: {e}")
            return False

    async def remove_label(self, issue_number: int, label_name: str) -> bool:
        """从 Issue 移除标签"""
        try:
            owner, repo = self.repo.split("/")
            url = f"{self.api_url}/repos/{owner}/{repo}/issues/{issue_number}/labels/{label_name}"

            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    url,
                    headers=self._get_headers(),
                    timeout=30,
                )
                response.raise_for_status()
                logger.info(f"Removed label '{label_name}' from issue #{issue_number}")
                return True

        except Exception as e:
            logger.error(f"Failed to remove label: {e}")
            return False

    async def close_issue(self, issue_number: int, comment: Optional[str] = None) -> bool:
        """关闭 Issue"""
        try:
            if comment:
                await self.create_comment(issue_number, comment)

            owner, repo = self.repo.split("/")
            url = f"{self.api_url}/repos/{owner}/{repo}/issues/{issue_number}"

            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    url,
                    headers=self._get_headers(),
                    json={"state": "closed"},
                    timeout=30,
                )
                response.raise_for_status()
                logger.info(f"Closed issue #{issue_number}")
                return True

        except Exception as e:
            logger.error(f"Failed to close issue: {e}")
            return False

    def parse_source_url(self, issue_body: str) -> Optional[str]:
        """
        从 Issue 内容解析源 URL

        支持格式：
        - URL: https://github.com/author/repo
        - source_url: https://github.com/author/repo
        - 仓库地址：https://...
        """
        patterns = [
            r"(?:URL|source_url|仓库地址|源地址)[:\s]*(https?://[^\s\n]+)",
            r"(https?://github\.com/[^\s\n]+)",
            r"(https?://gitlab\.com/[^\s\n]+)",
            r"(https?://[^/\s]+/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, issue_body, re.IGNORECASE)
            if match:
                url = match.group(1).strip()
                # 清理末尾标点
                url = url.rstrip(".,;:)")
                return url

        return None

    async def notify_approved(
        self,
        issue_number: int,
        skill_name: str,
        audit_summary: str,
    ) -> bool:
        """通知审核通过"""
        comment = f"""## ✅ 技能审核通过

**技能名称**: {skill_name}

**安全审计结果**: 通过
{audit_summary}

技能已自动合并到仓库，感谢您的贡献！
"""
        await self.add_label(issue_number, "approved")
        await self.remove_label(issue_number, "submission")
        return await self.close_issue(issue_number, comment)

    async def notify_rejected(
        self,
        issue_number: int,
        skill_name: str,
        reason: str,
        audit_findings: List[Dict] = None,
    ) -> bool:
        """通知审核拒绝"""
        findings_text = ""
        if audit_findings:
            findings_text = "\n\n**发现的问题**:\n"
            for f in audit_findings[:5]:  # 最多显示5个
                findings_text += f"- {f.get('title', '未知问题')}\n"

        comment = f"""## ❌ 技能审核拒绝

**技能名称**: {skill_name}

**拒绝原因**: {reason}
{findings_text}

请修复上述问题后重新提交。如有疑问，请在评论中说明。
"""
        await self.add_label(issue_number, "rejected")
        await self.remove_label(issue_number, "submission")
        return await self.close_issue(issue_number, comment)

    async def notify_processing(self, issue_number: int, skill_name: str) -> bool:
        """通知正在处理"""
        comment = f"""## 🔄 正在处理

**技能名称**: {skill_name}

正在进行安全审计，请稍候...
"""
        await self.add_label(issue_number, "processing")
        return await self.create_comment(issue_number, comment)

    async def notify_needs_review(
        self,
        issue_number: int,
        skill_name: str,
        audit_summary: str,
        risk_level: str,
    ) -> bool:
        """通知需要人工审核（中等风险）"""
        comment = f"""## ⚠️ 需要人工审核

**技能名称**: {skill_name}

**风险等级**: {risk_level}

**审计摘要**:
{audit_summary}

该技能存在中等风险，需要管理员手动审核。请耐心等待。
"""
        await self.add_label(issue_number, "needs-review")
        await self.remove_label(issue_number, "submission")
        return await self.create_comment(issue_number, comment)


# 单例实例
issue_handler: Optional[GiteaIssueHandler] = None


def get_issue_handler() -> GiteaIssueHandler:
    """获取 Issue 处理器实例"""
    global issue_handler
    if issue_handler is None:
        issue_handler = GiteaIssueHandler()
    return issue_handler
