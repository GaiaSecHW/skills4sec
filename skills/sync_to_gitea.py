#!/usr/bin/env python3
"""
批量同步 Skill 文件夹到 Gitea 组织仓库（含权限管理）

功能：
  - 自动为用户创建 Write 团队 + 加入公共 Read 团队
  - 远程仓库已存在 → 拉取（clone/pull）
  - 远程仓库不存在 → 创建仓库并上传文件
  - 每个用户只能读写自己的仓库，其他用户只读

用法：
  python sync_to_gitea.py --token TOKEN                          # 单 token，有管理权限则自动设置团队
  python sync_to_gitea.py --token TOKEN --admin-token TOKEN      # 指定单独的管理员 token
  python sync_to_gitea.py --token TOKEN --dry-run                # 仅检测

权限模型：
  组织
  ├── Owners          → Admin  → 所有仓库           → 管理员
  ├── dev-{user1}     → Write  → user1 的仓库        → 成员: user1
  ├── dev-{user2}     → Write  → user2 的仓库        → 成员: user2
  └── readers          → Read   → 所有仓库            → 所有普通用户
"""

import argparse
import base64
import os
import subprocess
import sys

try:
    import requests
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except ImportError:
    print("需要 requests 库，请运行: pip install requests")
    sys.exit(1)


# ──────────────────────────────────────────────
# 默认配置
# ──────────────────────────────────────────────

DEFAULT_CONFIG = {
    "gitea_url": "http://gitea.ai.icsl.huawei.com",
    "org": "icsl",
    "skills_dir": os.path.dirname(os.path.abspath(__file__)),
    "ssl_verify": False,
    "readers_team_name": "readers",
    "dev_team_prefix": "dev-",
}


# ──────────────────────────────────────────────
# Gitea API 封装
# ──────────────────────────────────────────────

class GiteaClient:
    def __init__(self, base_url, token, org, verify=False):
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v1"
        self.token = token
        self.org = org
        self.verify = verify
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"token {token}"})
        self.session.verify = verify
        # 绕过系统代理，直连内网 Gitea
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}

    def _url(self, path):
        return f"{self.api_url}{path}"

    def _get(self, path, **kwargs):
        return self.session.get(self._url(path), **kwargs)

    def _post(self, path, **kwargs):
        return self.session.post(self._url(path), **kwargs)

    def _put(self, path, **kwargs):
        return self.session.put(self._url(path), **kwargs)

    def _delete(self, path, **kwargs):
        return self.session.delete(self._url(path), **kwargs)

    # ── 用户 ──

    def get_current_user(self):
        resp = self._get("/user")
        resp.raise_for_status()
        return resp.json()

    # ── 组织成员 ──

    def is_org_member(self, username):
        """检查用户是否在组织中（属于任意团队）"""
        resp = self._get(f"/orgs/{self.org}/members/{username}")
        return resp.status_code == 204

    # ── 团队操作 ──

    def list_teams(self):
        """列出组织所有团队"""
        resp = self._get(f"/orgs/{self.org}/teams")
        resp.raise_for_status()
        return resp.json()

    def find_team_by_name(self, team_name):
        """按名称查找团队，返回团队信息或 None"""
        for team in self.list_teams():
            if team["name"] == team_name:
                return team
        return None

    def create_team(self, name, permission, description="", units=None):
        """创建团队"""
        if units is None:
            units = ["repo.code", "repo.issues", "repo.pulls"]
        if permission == "write":
            units.append("repo.releases")
        resp = self._post(
            f"/orgs/{self.org}/teams",
            json={
                "name": name,
                "description": description,
                "permission": permission,
                "units": units,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def ensure_team(self, name, permission, description=""):
        """确保团队存在，不存在则创建"""
        team = self.find_team_by_name(name)
        if team:
            return team
        return self.create_team(name, permission, description)

    def add_team_member(self, team_id, username):
        """添加用户到团队"""
        resp = self._put(f"/teams/{team_id}/members/{username}")
        return resp.status_code in (200, 204)

    def add_team_repo(self, team_id, repo_name):
        """关联仓库到团队"""
        resp = self._put(f"/teams/{team_id}/repos/{self.org}/{repo_name}")
        return resp.status_code in (200, 204)

    def get_team_members(self, team_id):
        """获取团队成员列表"""
        resp = self._get(f"/teams/{team_id}/members")
        if resp.status_code == 200:
            return [m["login"] for m in resp.json()]
        return []

    def get_team_repos(self, team_id):
        """获取团队关联的仓库列表"""
        resp = self._get(f"/teams/{team_id}/repos")
        if resp.status_code == 200:
            return [r["name"] for r in resp.json()]
        return []

    # ── 仓库操作 ──

    def repo_exists(self, repo_name):
        resp = self._get(f"/repos/{self.org}/{repo_name}")
        return resp.status_code == 200

    def create_repo(self, repo_name, private=True, description=""):
        resp = self._post(
            f"/org/{self.org}/repos",
            json={
                "name": repo_name,
                "private": private,
                "description": description,
                "auto_init": False,
            },
        )
        if resp.status_code == 403:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_repo_permissions(self, repo_name):
        """获取当前用户对仓库的权限"""
        resp = self._get(f"/repos/{self.org}/{repo_name}")
        if resp.status_code == 200:
            return resp.json().get("permissions", {})
        return {}

    # ── 文件操作 ──

    def get_file(self, repo_name, file_path):
        resp = self._get(f"/repos/{self.org}/{repo_name}/contents/{file_path}")
        if resp.status_code == 200:
            return resp.json()
        return None

    def create_file(self, repo_name, file_path, content_b64, message):
        resp = self._post(
            f"/repos/{self.org}/{repo_name}/contents/{file_path}",
            json={"message": message, "content": content_b64},
        )
        resp.raise_for_status()
        return resp.json()

    def update_file(self, repo_name, file_path, content_b64, message, sha):
        resp = self._put(
            f"/repos/{self.org}/{repo_name}/contents/{file_path}",
            json={"message": message, "content": content_b64, "sha": sha},
        )
        resp.raise_for_status()
        return resp.json()

    def upsert_file(self, repo_name, file_path, content_b64, message):
        existing = self.get_file(repo_name, file_path)
        if existing and "sha" in existing:
            return self.update_file(repo_name, file_path, content_b64, message, existing["sha"])
        return self.create_file(repo_name, file_path, content_b64, message)

    # ── Clone URL ──

    def clone_url(self, repo_name):
        return f"{self.base_url}/{self.org}/{repo_name}.git"


# ──────────────────────────────────────────────
# 文件工具
# ──────────────────────────────────────────────

def collect_files(directory):
    files = []
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [d for d in dirs if d != ".git"]
        for fname in filenames:
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, directory).replace("\\", "/")
            files.append(rel)
    return sorted(files)


def file_to_base64(filepath):
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ──────────────────────────────────────────────
# 核心流程
# ──────────────────────────────────────────────

def setup_user_permissions(admin_client, username, repo_names, dry_run=False):
    """
    为用户设置权限：
    1. 确保公共 readers 团队存在
    2. 为用户创建 dev-{username} 团队（Write）
    3. 将用户加入两个团队
    4. 将用户的仓库关联到 dev 团队，所有仓库关联到 readers 团队
    """
    # 1. 确保公共 readers 团队
    readers_team = admin_client.ensure_team(
        DEFAULT_CONFIG["readers_team_name"],
        permission="read",
        description="Read-only access to all repos",
    )
    print(f"  [READERS] 团队 ID: {readers_team['id']}")

    # 2. 为用户创建/确保 dev-{username} 团队
    dev_team_name = f"{DEFAULT_CONFIG['dev_team_prefix']}{username}"
    dev_team = admin_client.ensure_team(
        dev_team_name,
        permission="write",
        description=f"Write access for {username}'s repos",
    )
    print(f"  [DEV-{username}] 团队 ID: {dev_team['id']}")

    if dry_run:
        print(f"  [DRY-RUN] 将把 {username} 加入 {dev_team_name} 和 readers 团队")
        return

    # 3. 将用户加入两个团队
    admin_client.add_team_member(readers_team["id"], username)
    admin_client.add_team_member(dev_team["id"], username)
    print(f"  [OK] {username} 已加入 readers + {dev_team_name} 团队")

    # 4. 关联仓库
    for repo_name in repo_names:
        admin_client.add_team_repo(dev_team["id"], repo_name)
        admin_client.add_team_repo(readers_team["id"], repo_name)
        print(f"  [OK] {repo_name} 关联到 {dev_team_name}(Write) + readers(Read)")


def pull_repo(client, repo_name, local_path):
    url_with_token = client.clone_url(repo_name).replace(
        "https://", f"https://{client.token}@"
    )
    git_cmd = ["git", "-c", "http.sslVerify=false"]

    if os.path.isdir(os.path.join(local_path, ".git")):
        print(f"  [PULL] {local_path}")
        subprocess.run(git_cmd + ["pull", "--rebase"], cwd=local_path, capture_output=True)
    else:
        print(f"  [CLONE] -> {local_path}")
        subprocess.run(git_cmd + ["clone", url_with_token, local_path], capture_output=True)


def push_folder(client, repo_name, local_path, dry_run=False):
    files = collect_files(local_path)
    if not files:
        print(f"  [SKIP] 文件夹为空")
        return

    if dry_run:
        print(f"  [DRY-RUN] 将创建仓库并上传 {len(files)} 个文件:")
        for f in files:
            print(f"    - {f}")
        return

    if not client.repo_exists(repo_name):
        result = client.create_repo(repo_name)
        if result is None:
            print(f"  [ERROR] 无权限在 {client.org} 下创建仓库")
            return
        print(f"  [CREATE] 仓库 {client.org}/{repo_name} 已创建")

    success, failed = 0, 0
    for rel_path in files:
        abs_path = os.path.join(local_path, rel_path)
        content_b64 = file_to_base64(abs_path)
        try:
            client.upsert_file(repo_name, rel_path, content_b64, f"Add {rel_path}")
            print(f"    {rel_path}: OK")
            success += 1
        except Exception as e:
            print(f"    {rel_path}: FAILED - {e}")
            failed += 1

    print(f"  [DONE] {success}/{len(files)} 成功, {failed} 失败")


def sync_skills(user_client, admin_client, skills_dir, dry_run=False):
    entries = sorted(os.listdir(skills_dir))
    subdirs = [
        e for e in entries
        if os.path.isdir(os.path.join(skills_dir, e))
        and not e.startswith(".")
        and e not in ("__pycache__", "cc")
    ]

    if not subdirs:
        print("未发现任何子文件夹")
        return

    # 获取用户信息
    user_info = user_client.get_current_user()
    username = user_info["login"]
    print(f"用户: {username}\n")

    # 设置权限（需要管理员）
    if admin_client:
        print(f"{'='*50}")
        print(f"[权限设置]")
        setup_user_permissions(admin_client, username, subdirs, dry_run=dry_run)
        print()

    print(f"发现 {len(subdirs)} 个 skill 文件夹\n")

    for name in subdirs:
        local_path = os.path.join(skills_dir, name)
        print(f"{'='*50}")
        print(f"[{name}]")

        if user_client.repo_exists(name):
            print(f"  远程仓库已存在，执行拉取")
            if not dry_run:
                pull_repo(user_client, name, local_path)
            else:
                print(f"  [DRY-RUN] 将拉取 {name}")
        else:
            print(f"  远程仓库不存在，执行推送")
            push_folder(user_client, name, local_path, dry_run=dry_run)
        print()

    print(f"{'='*50}")
    print("同步完成")


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="批量同步 Skill 文件夹到 Gitea 组织（含权限管理）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 单 token 模式（token 有组织管理权限即可完成所有操作）
  python sync_to_gitea.py --token TOKEN

  # 仅预览
  python sync_to_gitea.py --token TOKEN --dry-run

  # 用户 token + 单独的管理员 token
  python sync_to_gitea.py --token TOKEN --admin-token ADMIN_TOKEN

  # 自定义参数
  python sync_to_gitea.py --token TOKEN --gitea-url https://gitea.example.com --org my-org

权限模型:
  自动为每个用户创建 dev-{username} 团队（Write），并加入公共 readers 团队（Read）。
  用户可读写自己的仓库，只能查看其他用户的仓库。
        """,
    )
    parser.add_argument("--token", required=True, help="Gitea API Token（有组织权限则无需 admin-token）")
    parser.add_argument("--admin-token", default=None,
                        help="管理员 Token（仅当 --token 无组织管理权限时需要）")
    parser.add_argument("--gitea-url", default=DEFAULT_CONFIG["gitea_url"], help="Gitea 地址")
    parser.add_argument("--org", default=DEFAULT_CONFIG["org"], help="组织名")
    parser.add_argument("--skills-dir", default=DEFAULT_CONFIG["skills_dir"], help="Skill 文件夹根目录")
    parser.add_argument("--dry-run", action="store_true", help="仅检测，不执行操作")
    args = parser.parse_args()

    if not os.path.isdir(args.skills_dir):
        print(f"错误: 目录不存在 - {args.skills_dir}")
        sys.exit(1)

    user_client = GiteaClient(args.gitea_url, args.token, args.org, verify=DEFAULT_CONFIG["ssl_verify"])

    # 检测 token 是否有组织管理权限
    has_org_admin = False
    try:
        user_client.get_current_user()
        teams = user_client.list_teams()
        has_org_admin = True
    except Exception:
        pass

    # 管理员 client：优先用 admin-token，否则复用主 token（如果有权限）
    if args.admin_token:
        admin_client = GiteaClient(args.gitea_url, args.admin_token, args.org, verify=DEFAULT_CONFIG["ssl_verify"])
    elif has_org_admin:
        admin_client = user_client  # 同一个 token 有管理权限，直接复用
    else:
        admin_client = None

    # 验证连接
    try:
        user_client.get_current_user()
    except Exception as e:
        print(f"错误: 无法连接 Gitea - {e}")
        sys.exit(1)

    print(f"Gitea:  {args.gitea_url}")
    print(f"组织:   {args.org}")
    print(f"目录:   {args.skills_dir}")
    if args.dry_run:
        print("模式:   DRY-RUN（仅检测）")
    print()

    sync_skills(user_client, admin_client, args.skills_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
