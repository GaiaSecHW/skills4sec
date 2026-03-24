"""
Gitea 辅助工具函数
"""
from app.models.submission import Submission


def build_issue_body(submission: Submission) -> str:
    """
    构建 Gitea Issue 内容

    Args:
        submission: 提交记录

    Returns:
        格式化的 Issue body 字符串
    """
    body_parts = [
        f"## 技能名称\n{submission.name}",
        f"## 仓库地址\n{submission.repo_url}",
        f"## 提交 ID\n`{submission.submission_id}`",
    ]

    if submission.category:
        body_parts.append(f"## 分类\n{submission.category}")

    body_parts.append(f"## 描述\n{submission.description or '无'}")

    if submission.contact:
        body_parts.append(f"## 联系方式\n{submission.contact}")

    return "\n\n".join(body_parts)
