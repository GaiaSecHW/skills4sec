"""
Git 操作服务 - 直接操作 Git 仓库

使用 gitpython 实现直接 Git 操作，不依赖 Gitea Actions
"""
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple, List
from datetime import datetime

from git import Repo, GitCommandError, GitError
from app.core import get_logger
from app.config import settings

logger = get_logger("git_ops")


class GitOpsService:
    """Git 操作服务"""

    def __init__(
        self,
        repo_url: Optional[str] = None,
        local_path: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        """
        初始化 Git 操作服务

        Args:
            repo_url: 远程仓库 URL（如 https://gitea.example.com/owner/repo.git）
            local_path: 本地仓库路径（None 则使用临时目录）
            access_token: 访问令牌（用于认证）
        """
        self.repo_url = repo_url or self._build_repo_url()
        self.local_path = local_path
        self.access_token = access_token or settings.GITEA_TOKEN
        self._repo: Optional[Repo] = None

    def _build_repo_url(self) -> str:
        """构建仓库 URL"""
        gitea_url = settings.GITEA_API_URL.replace("/api/v1", "")
        repo = settings.GITEA_REPO
        return f"{gitea_url}/{repo}.git"

    def _get_auth_url(self) -> str:
        """获取带认证的仓库 URL"""
        if self.access_token:
            # 在 URL 中注入 token
            # https://gitea.example.com/owner/repo.git -> https://token@gitea.example.com/owner/repo.git
            url = self.repo_url
            if "://" in url:
                protocol, rest = url.split("://", 1)
                return f"{protocol}://{self.access_token}@{rest}"
        return self.repo_url

    def _ensure_repo(self) -> Repo:
        """确保仓库可用"""
        if self._repo is not None:
            return self._repo

        if self.local_path and Path(self.local_path).exists():
            # 打开现有仓库
            self._repo = Repo(self.local_path)
            logger.info(f"Opened existing repo at {self.local_path}")
        else:
            # 克隆仓库到临时目录
            if self.local_path is None:
                self.local_path = tempfile.mkdtemp(prefix="skills4sec_")

            auth_url = self._get_auth_url()
            self._repo = Repo.clone_from(auth_url, self.local_path)
            logger.info(f"Cloned repo to {self.local_path}")

        return self._repo

    async def clone_or_pull(self) -> Tuple[bool, str]:
        """
        克隆或拉取最新代码

        Returns:
            (success, message)
        """
        try:
            repo = self._ensure_repo()

            if repo.heads:
                # 拉取最新代码
                origin = repo.remote(name="origin")
                origin.pull()
                logger.info(f"Pulled latest changes from origin")
                return True, "Pulled latest changes"
            else:
                return True, "Repo is empty or has no branches"

        except GitError as e:
            logger.error(f"Git operation failed: {e}")
            return False, str(e)

    async def create_branch(self, branch_name: str) -> Tuple[bool, str]:
        """
        创建新分支

        Args:
            branch_name: 分支名称

        Returns:
            (success, message)
        """
        try:
            repo = self._ensure_repo()

            # 检查分支是否已存在
            if branch_name in [h.name for h in repo.heads]:
                # 切换到现有分支
                repo.git.checkout(branch_name)
                return True, f"Switched to existing branch: {branch_name}"

            # 创建并切换到新分支
            repo.git.checkout("-b", branch_name)
            logger.info(f"Created and switched to branch: {branch_name}")
            return True, f"Created branch: {branch_name}"

        except GitError as e:
            logger.error(f"Failed to create branch: {e}")
            return False, str(e)

    async def add_skill_files(
        self,
        skill_dir: Path,
        target_path: str,
        author: str,
        slug: str,
    ) -> Tuple[bool, str]:
        """
        添加 skill 文件到仓库

        Args:
            skill_dir: skill 源目录
            target_path: 目标路径（pending 或 skills）
            author: 作者
            slug: skill slug

        Returns:
            (success, message)
        """
        try:
            repo = self._ensure_repo()

            # 构建目标目录
            dest_dir = Path(self.local_path) / target_path / author / slug

            # 创建目录（如果不存在）
            dest_dir.mkdir(parents=True, exist_ok=True)

            # 复制文件
            for item in skill_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, dest_dir / item.name)
                elif item.is_dir() and item.name not in [".git", "__pycache__"]:
                    shutil.copytree(item, dest_dir / item.name, dirs_exist_ok=True)

            # 添加到暂存区
            repo.index.add([str(dest_dir.relative_to(self.local_path))])

            logger.info(f"Added skill files to {target_path}/{author}/{slug}")
            return True, f"Added files to {target_path}/{author}/{slug}"

        except Exception as e:
            logger.error(f"Failed to add skill files: {e}")
            return False, str(e)

    async def commit_and_push(
        self,
        message: str,
        retry: int = 3,
    ) -> Tuple[bool, str]:
        """
        提交并推送更改

        Args:
            message: 提交消息
            retry: 重试次数

        Returns:
            (success, message)
        """
        try:
            repo = self._ensure_repo()

            # 检查是否有变更
            if not repo.is_dirty(untracked_files=True):
                return True, "No changes to commit"

            # 提交
            repo.index.commit(message)
            logger.info(f"Committed: {message}")

            # 推送（带重试）
            for attempt in range(retry):
                try:
                    origin = repo.remote(name="origin")
                    auth_url = self._get_auth_url()
                    origin.set_url(auth_url)
                    origin.push()
                    logger.info(f"Pushed to origin")
                    return True, "Pushed successfully"
                except GitCommandError as e:
                    if attempt < retry - 1:
                        logger.warning(f"Push failed (attempt {attempt + 1}), retrying...")
                        time.sleep(2 ** attempt)  # 指数退避
                        # 拉取远程变更后重试
                        origin.pull(rebase=True)
                    else:
                        raise e

        except GitError as e:
            logger.error(f"Failed to commit and push: {e}")
            return False, str(e)

    async def merge_to_main(
        self,
        branch_name: str,
        delete_branch: bool = True,
    ) -> Tuple[bool, str]:
        """
        合并分支到 main

        Args:
            branch_name: 要合并的分支名
            delete_branch: 是否删除源分支

        Returns:
            (success, message)
        """
        try:
            repo = self._ensure_repo()

            # 切换到 main 分支
            repo.git.checkout("main")

            # 合并分支
            repo.git.merge(branch_name)
            logger.info(f"Merged {branch_name} into main")

            # 推送 main
            origin = repo.remote(name="origin")
            auth_url = self._get_auth_url()
            origin.set_url(auth_url)
            origin.push()

            # 删除分支（可选）
            if delete_branch:
                repo.delete_head(branch_name, force=True)
                origin.push(refspec=f":{branch_name}")  # 删除远程分支
                logger.info(f"Deleted branch: {branch_name}")

            return True, f"Merged {branch_name} into main"

        except GitError as e:
            logger.error(f"Failed to merge to main: {e}")
            return False, str(e)

    async def move_skill(
        self,
        from_path: str,
        to_path: str,
    ) -> Tuple[bool, str]:
        """
        移动 skill 目录（如 pending → skills）

        Args:
            from_path: 源路径（如 pending/author/slug）
            to_path: 目标路径（如 skills/author/slug）

        Returns:
            (success, message)
        """
        try:
            repo = self._ensure_repo()
            local = Path(self.local_path)

            src = local / from_path
            dst = local / to_path

            if not src.exists():
                return False, f"Source path not found: {from_path}"

            # 创建目标目录
            dst.parent.mkdir(parents=True, exist_ok=True)

            # 移动目录
            shutil.move(str(src), str(dst))

            # 删除空目录
            self._cleanup_empty_dirs(src.parent)

            # 添加变更到暂存区
            repo.index.add([str(dst.relative_to(local))])
            if src.exists():
                repo.index.remove([str(src.relative_to(local))], r=True)

            logger.info(f"Moved skill from {from_path} to {to_path}")
            return True, f"Moved to {to_path}"

        except Exception as e:
            logger.error(f"Failed to move skill: {e}")
            return False, str(e)

    def _cleanup_empty_dirs(self, path: Path):
        """清理空目录"""
        try:
            while path != Path(self.local_path):
                if path.exists() and not any(path.iterdir()):
                    path.rmdir()
                    path = path.parent
                else:
                    break
        except Exception:
            pass

    async def file_exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        try:
            repo = self._ensure_repo()
            full_path = Path(self.local_path) / file_path
            return full_path.exists()
        except Exception:
            return False

    async def read_file(self, file_path: str) -> Optional[str]:
        """读取文件内容"""
        try:
            repo = self._ensure_repo()
            full_path = Path(self.local_path) / file_path
            if full_path.exists():
                return full_path.read_text(encoding="utf-8")
            return None
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            return None

    def cleanup(self):
        """清理临时目录"""
        if self.local_path and self.local_path.startswith(tempfile.gettempdir()):
            try:
                shutil.rmtree(self.local_path)
                logger.info(f"Cleaned up temp directory: {self.local_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup: {e}")


# 单例实例
git_ops_service: Optional[GitOpsService] = None


def get_git_ops() -> GitOpsService:
    """获取 Git 操作服务实例"""
    global git_ops_service
    if git_ops_service is None:
        git_ops_service = GitOpsService()
    return git_ops_service
