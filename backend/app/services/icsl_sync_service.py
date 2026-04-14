"""
ICSL 组织 Skill 同步服务

职责:
1. 从 icsl 组织拉取所有 skill 仓库的最新版本 (tag)
2. 将本地 skill 推送到 icsl 组织 (创建/更新仓库 + tag)
3. 管理 webhook 回调
4. 触发 rebuild_site 更新前端数据
"""
import asyncio
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings
from app.core import get_logger

logger = get_logger("icsl_sync")


class ICSLSyncService:
    """ICSL 组织同步服务"""

    def __init__(self):
        self.api_url = settings.ICSL_GITEA_API_URL
        self.token = settings.ICSL_GITEA_TOKEN
        self.org_name = settings.ICSL_ORG_NAME

        # data_dir: 配置了 ICSL_DATA_DIR 用该路径, 否则用项目根目录下的 data/
        if settings.ICSL_DATA_DIR:
            self.data_dir = Path(settings.ICSL_DATA_DIR)
        else:
            _project_root = Path(__file__).resolve().parent.parent.parent.parent
            self.data_dir = _project_root / "data"

        # 关键目录
        self.skills_dir = self.data_dir / "skills"
        self.harnesses_dir = self.data_dir / "harnesses"
        self.agents_dir = self.data_dir / "agents"
        self.docs_dir = self.data_dir / "docs"
        self.docs_data_dir = self.docs_dir / "data"

        # 同步状态文件
        self.sync_state_file = self.data_dir / "sync_state.json"

        # 确保目录存在 (仅在配置了 ICSL 同步时创建)
        if self._is_configured():
            self.skills_dir.mkdir(parents=True, exist_ok=True)
            self.docs_data_dir.mkdir(parents=True, exist_ok=True)

        # Gitea clone 基地址 (从 API URL 推导)
        # http://xxx:3000/api/v1 -> http://xxx:3000
        self._gitea_base = self.api_url.rstrip("/").removesuffix("/api/v1")

    def _headers(self) -> dict:
        return {
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json",
        }

    def _is_configured(self) -> bool:
        return bool(self.api_url and self.token)

    # ============================================================
    #  辅助: 异步子进程
    # ============================================================

    @staticmethod
    async def _run_git(cmd: list, timeout: int = 120, cwd: str = None) -> Tuple[int, str, str]:
        """异步执行 git 命令"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            return (
                process.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise

    # ============================================================
    #  1. 拉取: 从 icsl 组织同步 skill
    # ============================================================

    async def full_sync(self) -> Dict[str, Any]:
        """
        全量同步: 遍历 icsl 组织所有仓库, 拉取最新 tag

        Returns:
            {"synced": int, "skipped": int, "errors": int, "details": [...]}
        """
        if not self._is_configured():
            return {"synced": 0, "skipped": 0, "errors": 0, "details": [], "error": "not configured"}

        repos = await self._list_org_repos()
        if repos is None:
            return {"synced": 0, "skipped": 0, "errors": 0, "details": [], "error": "failed to list repos"}

        results = {"synced": 0, "skipped": 0, "errors": 0, "details": []}

        for repo in repos:
            repo_name = repo["name"]
            try:
                success, msg = await self.sync_single_repo(repo_name)
                if success:
                    results["synced"] += 1
                elif "skipped" in msg:
                    results["skipped"] += 1
                else:
                    results["errors"] += 1
                results["details"].append({"repo": repo_name, "success": success, "message": msg})
            except Exception as e:
                results["errors"] += 1
                results["details"].append({"repo": repo_name, "success": False, "message": str(e)})
                logger.error(f'{{"event": "sync_repo_error", "repo": "{repo_name}", "error": "{e}"}}')

        # 全量同步完成后, 重新构建前端数据
        if results["synced"] > 0:
            await self.rebuild_site()

        logger.info(
            f'{{"event": "full_sync_done", "synced": {results["synced"]}, '
            f'"skipped": {results["skipped"]}, "errors": {results["errors"]}}}'
        )
        return results

    async def sync_single_repo(self, repo_name: str) -> Tuple[bool, str]:
        """
        同步单个仓库: 获取最新 tag -> clone 到 skills/{repo_name}/

        Returns:
            (是否成功, 消息)
        """
        # 1. 获取最新 tag
        latest_tag = await self._get_latest_tag(repo_name)
        if not latest_tag:
            return False, f"skipped: no tags in {repo_name}"

        # 2. 检查是否需要更新
        if not await self._should_update(repo_name, latest_tag):
            return False, f"skipped: {repo_name} already at {latest_tag}"

        # 3. 克隆指定 tag
        success, msg = await self._clone_repo_at_tag(repo_name, latest_tag)
        if success:
            # 4. 更新同步状态
            state = self._load_sync_state()
            state[repo_name] = latest_tag
            self._save_sync_state(state)

        return success, msg

    async def _list_org_repos(self) -> Optional[List[Dict]]:
        """获取 icsl 组织的所有仓库列表"""
        repos = []
        page = 1
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                resp = await client.get(
                    f"{self.api_url}/orgs/{self.org_name}/repos",
                    headers=self._headers(),
                    params={"page": page, "limit": 50},
                )
                if resp.status_code != 200:
                    logger.error(
                        f'{{"event": "list_repos_failed", "status": {resp.status_code}, '
                        f'"body": "{resp.text[:200]}"}}'
                    )
                    return None
                batch = resp.json()
                if not batch:
                    break
                repos.extend(batch)
                page += 1
        return repos

    async def _get_latest_tag(self, repo_name: str) -> Optional[str]:
        """获取仓库最新 tag"""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.api_url}/repos/{self.org_name}/{repo_name}/tags",
                headers=self._headers(),
                params={"limit": 1},
            )
            if resp.status_code != 200:
                return None
            tags = resp.json()
            if not tags:
                return None
            return tags[0].get("name")

    async def _should_update(self, repo_name: str, latest_tag: str) -> bool:
        """判断是否需要更新 (对比 sync_state 中记录的版本)"""
        state = self._load_sync_state()
        current = state.get(repo_name)
        if not current:
            return True
        return current != latest_tag

    async def _clone_repo_at_tag(self, repo_name: str, tag: str) -> Tuple[bool, str]:
        """
        克隆仓库指定 tag 到 skills/{repo_name}/

        使用 git clone --branch {tag} --depth 1 浅克隆
        """
        clone_url = f"{self._gitea_base}/{self.org_name}/{repo_name}.git"
        # token 注入 URL
        auth_url = clone_url.replace("://", f"://{{self.token}}@", 1)

        target_dir = self.skills_dir / repo_name

        # 如果目标目录已存在, 先删除
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)

        cmd = ["git", "clone", "--branch", tag, "--depth", "1", auth_url, str(target_dir)]
        returncode, stdout, stderr = await self._run_git(cmd, timeout=120)

        if returncode != 0:
            return False, f"clone failed: {stderr[:200]}"

        # 验证 SKILL.md 存在
        if not (target_dir / "SKILL.md").exists():
            shutil.rmtree(target_dir, ignore_errors=True)
            return False, f"SKILL.md not found in {repo_name}@{tag}"

        return True, f"synced {repo_name}@{tag}"

    # ============================================================
    #  2. 推送: 将本地 skill 推送到 icsl 组织
    # ============================================================

    async def push_skill(self, slug: str) -> Tuple[bool, str]:
        """
        推送单个 skill 到 icsl 组织

        流程:
        1. 确保 icsl 组织存在
        2. 检查同名仓库是否存在
           - 不存在: 创建仓库, tag=v1.0.0
           - 存在: 推导下一个版本号
        3. 推送内容 + 打 tag
        4. 更新 sync_state
        """
        if not self._is_configured():
            return False, "ICSL sync not configured"

        skill_dir = self.skills_dir / slug
        if not skill_dir.exists():
            return False, f"skill not found: {slug}"

        # 1. 确保组织存在
        if not await self._ensure_org_exists():
            return False, "failed to ensure org exists"

        # 2. 检查仓库是否存在
        repo_exists = await self._check_repo_exists(slug)

        if not repo_exists:
            success, msg = await self._create_repo(slug)
            if not success:
                return False, msg
            tag = "v1.0.0"
        else:
            existing_tags = await self._get_repo_tags(slug)
            tag = self._derive_next_tag(existing_tags)

        # 3. 推送到仓库
        success, msg = await self._push_to_repo(slug, skill_dir, tag)

        if success:
            state = self._load_sync_state()
            state[slug] = tag
            self._save_sync_state(state)

        return success, msg

    async def _ensure_org_exists(self) -> bool:
        """确保 icsl 组织存在"""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.api_url}/orgs/{self.org_name}",
                headers=self._headers(),
            )
            if resp.status_code == 200:
                return True
            if resp.status_code == 404:
                # 尝试创建组织
                resp = await client.post(
                    f"{self.api_url}/orgs",
                    headers=self._headers(),
                    json={
                        "username": self.org_name,
                        "full_name": self.org_name,
                        "visibility": "private",
                    },
                )
                if resp.status_code in (201, 200):
                    logger.info(f'{{"event": "org_created", "org": "{self.org_name}"}}')
                    return True
                logger.error(f'{{"event": "org_create_failed", "status": {resp.status_code}}}')
                return False
            return False

    async def _check_repo_exists(self, repo_name: str) -> bool:
        """检查仓库是否已存在"""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.api_url}/repos/{self.org_name}/{repo_name}",
                headers=self._headers(),
            )
            return resp.status_code == 200

    async def _create_repo(self, repo_name: str) -> Tuple[bool, str]:
        """在 icsl 组织下创建仓库"""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self.api_url}/orgs/{self.org_name}/repos",
                headers=self._headers(),
                json={
                    "name": repo_name,
                    "description": f"Skill: {repo_name}",
                    "private": False,
                    "auto_init": False,
                },
            )
            if resp.status_code in (201, 200):
                return True, f"repo {repo_name} created"
            return False, f"create repo failed: {resp.status_code} {resp.text[:200]}"

    async def _get_repo_tags(self, repo_name: str) -> List[str]:
        """获取仓库所有 tags"""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.api_url}/repos/{self.org_name}/{repo_name}/tags",
                headers=self._headers(),
                params={"limit": 100},
            )
            if resp.status_code != 200:
                return []
            return [t.get("name", "") for t in resp.json()]

    def _derive_next_tag(self, existing_tags: List[str]) -> str:
        """
        根据已有 tags 推导下一个版本号

        策略: 取最高版本号 +1 patch, 如 v1.0.0 -> v1.0.1
        无已有 tag 则返回 v1.0.0
        """
        if not existing_tags:
            return "v1.0.0"

        versions = []
        for tag in existing_tags:
            match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", tag)
            if match:
                versions.append((int(match.group(1)), int(match.group(2)), int(match.group(3))))

        if not versions:
            return "v1.0.0"

        versions.sort(reverse=True)
        major, minor, patch = versions[0]
        return f"v{major}.{minor}.{patch + 1}"

    async def _push_to_repo(
        self, repo_name: str, skill_dir: Path, tag: str
    ) -> Tuple[bool, str]:
        """
        将 skill 目录推送到仓库

        流程: git init -> remote add -> add . -> commit -> tag -> push
        """
        clone_url = f"{self._gitea_base}/{self.org_name}/{repo_name}.git"
        auth_url = clone_url.replace("://", f"://{{self.token}}@", 1)

        # 使用临时目录进行 git 操作
        tmp_dir = self.data_dir / f".tmp_push_{repo_name}"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

        try:
            # 如果远程仓库已有内容, 先 clone 下来
            repo_exists = await self._check_repo_exists(repo_name)
            if repo_exists:
                # 尝试 clone 现有仓库
                rc, _, _ = await self._run_git(
                    ["git", "clone", "--depth", "1", auth_url, str(tmp_dir)],
                    timeout=60,
                )
                if rc == 0:
                    # 复制 skill 内容到临时目录
                    for item in skill_dir.iterdir():
                        dest = tmp_dir / item.name
                        if dest.is_dir():
                            shutil.rmtree(dest, ignore_errors=True)
                        elif dest.exists():
                            dest.unlink()
                        if item.is_dir():
                            shutil.copytree(item, dest)
                        else:
                            shutil.copy2(item, dest)
                else:
                    # clone 失败, 直接用 skill 目录
                    shutil.copytree(skill_dir, tmp_dir)
            else:
                shutil.copytree(skill_dir, tmp_dir)

            # git init (如果还没有 .git)
            if not (tmp_dir / ".git").exists():
                await self._run_git(["git", "init"], cwd=str(tmp_dir))

            # git remote add origin
            rc, _, stderr = await self._run_git(
                ["git", "remote", "add", "origin", auth_url],
                cwd=str(tmp_dir),
            )
            if rc != 0 and "already exists" not in stderr:
                # remote 可能已存在, 尝试 set-url
                await self._run_git(
                    ["git", "remote", "set-url", "origin", auth_url],
                    cwd=str(tmp_dir),
                )

            # git add .
            await self._run_git(["git", "add", "."], cwd=str(tmp_dir))

            # git commit
            rc, _, stderr = await self._run_git(
                ["git", "commit", "-m", f"update skill {repo_name} ({tag})"],
                cwd=str(tmp_dir),
            )
            # nothing to commit 是正常的
            if rc != 0 and "nothing to commit" not in stderr and "no changes added" not in stderr:
                # 可能没有变更
                pass

            # git tag
            await self._run_git(["git", "tag", tag], cwd=str(tmp_dir))

            # git push origin main --tags --force
            rc, _, stderr = await self._run_git(
                ["git", "push", "origin", "HEAD:main", "--tags", "--force"],
                cwd=str(tmp_dir),
                timeout=120,
            )
            if rc != 0:
                return False, f"push failed: {stderr[:200]}"

            return True, f"pushed {repo_name}@{tag}"

        finally:
            # 清理临时目录
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

    # ============================================================
    #  3. 查重
    # ============================================================

    async def check_name_conflict(self, slug: str) -> Tuple[bool, Optional[Dict]]:
        """
        检查 skill 是否在 icsl 组织已存在同名仓库

        Returns:
            (是否存在冲突, 冲突仓库信息 or None)
        """
        if not self._is_configured():
            return False, None

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.api_url}/repos/{self.org_name}/{slug}",
                headers=self._headers(),
            )
            if resp.status_code == 200:
                repo = resp.json()
                return True, {
                    "name": repo.get("name"),
                    "url": repo.get("html_url"),
                    "updated_at": repo.get("updated_at"),
                }
            return False, None

    # ============================================================
    #  4. Webhook 处理
    # ============================================================

    async def handle_webhook(self, payload: dict) -> Dict[str, Any]:
        """
        处理 Gitea Organization Webhook

        根据 event type:
        - create (tag): 同步对应仓库
        - push: 同步对应仓库
        """
        repo_info = payload.get("repository") or {}
        repo_name = repo_info.get("name")

        if not repo_name:
            return {"status": "ignored", "reason": "no repo name"}

        ref = payload.get("ref", "")
        ref_type = payload.get("ref_type", "")

        # tag 创建事件
        if ref_type == "tag":
            success, msg = await self.sync_single_repo(repo_name)
            if success:
                await self.rebuild_site()
            return {"status": "synced" if success else "skipped", "repo": repo_name, "message": msg}

        # push 事件 (main 分支)
        if ref == "refs/heads/main" or payload.get("pusher"):
            success, msg = await self.sync_single_repo(repo_name)
            if success:
                await self.rebuild_site()
            return {"status": "synced" if success else "skipped", "repo": repo_name, "message": msg}

        return {"status": "ignored", "reason": f"unhandled event: ref={ref}, ref_type={ref_type}"}

    async def register_org_webhook(self, target_url: str) -> Tuple[bool, str]:
        """
        为 icsl 组织注册 Webhook

        Args:
            target_url: backend 的 webhook 接收地址, 如 https://skillhub.ai.icsl.huawei.com/api/icsl/webhook
        """
        if not self._is_configured():
            return False, "not configured"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self.api_url}/orgs/{self.org_name}/hooks",
                headers=self._headers(),
                json={
                    "type": "gitea",
                    "config": {
                        "url": target_url,
                        "content_type": "json",
                    },
                    "events": ["push", "create"],
                    "active": True,
                },
            )
            if resp.status_code in (201, 200):
                return True, "webhook registered"
            return False, f"register webhook failed: {resp.status_code} {resp.text[:200]}"

    # ============================================================
    #  5. Build Site (Python 版 build-site.js)
    # ============================================================

    async def rebuild_site(self) -> Tuple[bool, str]:
        """
        重新生成前端数据文件

        扫描 /data/skills/ 下所有 skill, 生成:
        - /data/docs/data/skills.json
        - /data/docs/data/diffs/{slug}/*.diff
        - /data/docs/.nojekyll
        """
        try:
            skills = self._collect_skills()
            self._write_skills_json(skills)
            self._copy_diffs(skills)

            # 确保 .nojekyll
            (self.docs_dir / ".nojekyll").touch(exist_ok=True)

            logger.info(f'{{"event": "rebuild_site", "skills": {len(skills)}}}')
            return True, f"rebuilt with {len(skills)} skills"
        except Exception as e:
            logger.error(f'{{"event": "rebuild_site_error", "error": "{e}"}}')
            return False, str(e)

    def _collect_skills(self) -> List[Dict]:
        """扫描 skills/ 目录, 收集所有 skill 的 skill-report.json"""
        skills = []

        if not self.skills_dir.exists():
            return skills

        risk_rank = {"safe": 0, "low": 1, "medium": 2, "high": 3}

        for entry in sorted(self.skills_dir.iterdir()):
            if not entry.is_dir():
                continue

            report_path = entry / "skill-report.json"
            if not report_path.exists():
                logger.warning(f'{{"event": "no_report", "dir": "{entry.name}"}}')
                continue

            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(f'{{"event": "bad_report", "dir": "{entry.name}", "error": "{e}"}}')
                continue

            s = report.get("skill", {})
            sa = report.get("security_audit", {})
            c = report.get("content", {})
            m = report.get("meta", {})

            if not s.get("name"):
                continue

            # 收集 .diff 文件
            diff_dir = entry / ".diff"
            diffs = []
            if diff_dir.exists():
                diffs = sorted(
                    f.name for f in diff_dir.iterdir()
                    if f.is_file() and f.name.endswith(".diff")
                )

            skills.append({
                "_dir": entry.name,
                "slug": m.get("slug") or entry.name,
                "name": s.get("name"),
                "summary": s.get("summary") or s.get("description") or "",
                "description": s.get("description") or "",
                "icon": s.get("icon", "📦"),
                "version": s.get("version", "1.0.0"),
                "author": s.get("author", "unknown"),
                "license": s.get("license", ""),
                "category": s.get("category", ""),
                "tags": s.get("tags", []),
                "supported_tools": s.get("supported_tools", []),
                "risk_factors": s.get("risk_factors", []),
                "risk_level": sa.get("risk_level", "safe"),
                "is_blocked": sa.get("is_blocked", False),
                "safe_to_publish": sa.get("safe_to_publish", True),
                "source_url": m.get("source_url", ""),
                "source_type": m.get("source_type", ""),
                "generated_at": m.get("generated_at", ""),
                "user_title": c.get("user_title", ""),
                "value_statement": c.get("value_statement", ""),
                "actual_capabilities": c.get("actual_capabilities", []),
                "use_cases": c.get("use_cases", []),
                "prompt_templates": c.get("prompt_templates", []),
                "limitations": c.get("limitations", []),
                "faq": c.get("faq", []),
                "diffs": diffs,
            })

        # 排序: 风险等级安全优先, 然后字母序
        skills.sort(key=lambda x: (risk_rank.get(x.get("risk_level", "safe"), 9), x.get("name", "")))
        return skills

    def _write_skills_json(self, skills: List[Dict]):
        """写入 skills.json"""
        self.docs_data_dir.mkdir(parents=True, exist_ok=True)
        dest = self.docs_data_dir / "skills.json"
        dest.write_text(json.dumps(skills, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _copy_diffs(self, skills: List[Dict]):
        """复制 .diff 文件到 docs/data/diffs/{slug}/"""
        for skill in skills:
            if not skill.get("diffs"):
                continue
            src_dir = self.skills_dir / skill["_dir"] / ".diff"
            dest_dir = self.docs_data_dir / "diffs" / skill["slug"]
            dest_dir.mkdir(parents=True, exist_ok=True)
            for fname in skill["diffs"]:
                src_file = src_dir / fname
                dest_file = dest_dir / fname
                if src_file.exists():
                    shutil.copy2(src_file, dest_file)

    # ============================================================
    #  6. 同步状态管理
    # ============================================================

    def _load_sync_state(self) -> Dict[str, str]:
        """加载同步状态: {repo_name: current_tag}"""
        if self.sync_state_file.exists():
            try:
                return json.loads(self.sync_state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {}
        return {}

    def _save_sync_state(self, state: Dict[str, str]):
        """保存同步状态"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sync_state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # ============================================================
    #  7. 状态查询
    # ============================================================

    def get_sync_status(self) -> Dict[str, Any]:
        """获取同步状态摘要"""
        state = self._load_sync_state()
        # 统计本地 skills 目录
        local_skills = []
        if self.skills_dir.exists():
            local_skills = [
                d.name for d in self.skills_dir.iterdir()
                if d.is_dir() and (d / "skill-report.json").exists()
            ]
        return {
            "configured": self._is_configured(),
            "org_name": self.org_name,
            "synced_repos": state,
            "total_synced": len(state),
            "local_skills_count": len(local_skills),
        }


# 单例
icsl_sync_service = ICSLSyncService()
