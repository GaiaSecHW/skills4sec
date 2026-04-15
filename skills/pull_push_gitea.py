#!/usr/bin/env python3
"""
Gitea 组织仓库双向同步

流程：
  1. 拉取组织下所有已有仓库到本地（clone/pull）
  2. 将本地新增的仓库推送到组织（创建 + 上传文件）

用法：
  python pull_push_gitea.py --token TOKEN --local-dir ./skills
  python pull_push_gitea.py --token TOKEN --local-dir ./skills --dry-run
  python pull_push_gitea.py --token TOKEN --local-dir ./skills --push-only
  python pull_push_gitea.py --token TOKEN --local-dir ./skills --pull-only
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

DEFAULT_CONFIG = {
    "gitea_url": "http://gitea.ai.icsl.huawei.com",
    "org": "icsl",
    "ssl_verify": False,
    "repo_private": False,  # 默认创建公开仓库
}

# 排除的目录名
EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", ".idea", ".vscode"}


class GiteaClient:
    def __init__(self, base_url, token, org, verify=False):
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/v1"
        self.token = token
        self.org = org
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"token {token}"})
        self.session.verify = verify
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}

    def _url(self, path):
        return f"{self.api_url}{path}"

    def get_current_user(self):
        resp = self.session.get(self._url("/user"))
        resp.raise_for_status()
        return resp.json()

    def list_repos(self):
        """列出组织下所有仓库名"""
        repos = []
        page = 1
        while True:
            resp = self.session.get(
                self._url(f"/orgs/{self.org}/repos"),
                params={"page": page, "limit": 50},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            repos.extend(data)
            page += 1
        return [r["name"] for r in repos]

    def repo_exists(self, repo_name):
        resp = self.session.get(self._url(f"/repos/{self.org}/{repo_name}"))
        return resp.status_code == 200

    def create_repo(self, repo_name, private=False):
        resp = self.session.post(
            self._url(f"/org/{self.org}/repos"),
            json={"name": repo_name, "private": private, "auto_init": False},
        )
        if resp.status_code == 403:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_file(self, repo_name, file_path):
        resp = self.session.get(
            self._url(f"/repos/{self.org}/{repo_name}/contents/{file_path}")
        )
        if resp.status_code == 200:
            return resp.json()
        return None

    def create_file(self, repo_name, file_path, content_b64, message):
        resp = self.session.post(
            self._url(f"/repos/{self.org}/{repo_name}/contents/{file_path}"),
            json={"message": message, "content": content_b64},
        )
        resp.raise_for_status()
        return resp.json()

    def update_file(self, repo_name, file_path, content_b64, message, sha):
        resp = self.session.put(
            self._url(f"/repos/{self.org}/{repo_name}/contents/{file_path}"),
            json={"message": message, "content": content_b64, "sha": sha},
        )
        resp.raise_for_status()
        return resp.json()

    def upsert_file(self, repo_name, file_path, content_b64, message):
        existing = self.get_file(repo_name, file_path)
        if existing and "sha" in existing:
            return self.update_file(repo_name, file_path, content_b64, message, existing["sha"])
        return self.create_file(repo_name, file_path, content_b64, message)

    def clone_url(self, repo_name):
        return f"{self.base_url}/{self.org}/{repo_name}.git"

    def clone_url_with_token(self, repo_name):
        return f"https://{self.token}@{self.base_url.replace('https://', '')}/{self.org}/{repo_name}.git"


# ──────────────────────────────────────────────
# 文件工具
# ──────────────────────────────────────────────

def collect_files(directory):
    """收集目录下所有文件相对路径"""
    files = []
    for root, dirs, filenames in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fname in filenames:
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, directory).replace("\\", "/")
            files.append(rel)
    return sorted(files)


def file_to_base64(filepath):
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def list_local_dirs(local_dir):
    """列出本地目录下的所有子文件夹"""
    if not os.path.isdir(local_dir):
        return []
    return sorted([
        e for e in os.listdir(local_dir)
        if os.path.isdir(os.path.join(local_dir, e))
        and not e.startswith(".")
        and e not in ("__pycache__", "node_modules")
    ])


# ──────────────────────────────────────────────
# Pull 操作
# ──────────────────────────────────────────────

def pull_repos(client, remote_repos, local_dir, dry_run=False):
    """拉取远程所有仓库到本地"""
    print(f"{'='*60}")
    print(f"[PULL] 拉取远程仓库到本地")
    print(f"{'='*60}")
    print(f"远程仓库: {len(remote_repos)} 个\n")

    success, skipped, failed = 0, 0, 0

    for i, repo_name in enumerate(sorted(remote_repos), 1):
        local_path = os.path.join(local_dir, repo_name)
        print(f"  [{i}/{len(remote_repos)}] {repo_name}")

        if dry_run:
            if os.path.isdir(local_path):
                print(f"       -> PULL (已存在)")
            else:
                print(f"       -> CLONE (新)")
            success += 1
            continue

        try:
            if os.path.isdir(os.path.join(local_path, ".git")):
                # 已存在，pull
                result = subprocess.run(
                    ["git", "-c", "http.sslVerify=false", "pull", "--rebase"],
                    cwd=local_path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    print(f"       -> PULL OK")
                else:
                    print(f"       -> PULL WARN: {result.stderr.strip()[:80]}")
                success += 1
            else:
                # 不存在，clone
                url = client.clone_url_with_token(repo_name)
                result = subprocess.run(
                    ["git", "clone", "-c", "http.sslVerify=false", url, local_path],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    print(f"       -> CLONE OK")
                    success += 1
                else:
                    # clone 可能因代理问题失败，用 API 下载
                    print(f"       -> CLONE 失败，尝试 API 下载...")
                    if api_pull_repo(client, repo_name, local_path):
                        print(f"       -> API 下载 OK")
                        success += 1
                    else:
                        print(f"       -> API 下载 FAILED")
                        failed += 1
        except Exception as e:
            print(f"       -> FAILED: {e}")
            failed += 1

    print(f"\n  结果: {success} 成功, {skipped} 跳过, {failed} 失败\n")


def api_pull_repo(client, repo_name, local_path):
    """通过 API 下载仓库文件（git clone 失败时的后备方案）"""
    try:
        # 获取仓库根目录文件列表
        resp = client.session.get(
            client._url(f"/repos/{client.org}/{repo_name}/contents/")
        )
        if resp.status_code != 200:
            return False

        items = resp.json()
        os.makedirs(local_path, exist_ok=True)

        for item in items:
            if item["type"] == "file":
                download_file(client, repo_name, item["path"], local_path)
            elif item["type"] == "dir":
                download_dir(client, repo_name, item["path"], local_path)
        return True
    except Exception:
        return False


def download_file(client, repo_name, file_path, local_dir):
    """通过 API 下载单个文件"""
    resp = client.session.get(
        client._url(f"/repos/{client.org}/{repo_name}/contents/{file_path}")
    )
    if resp.status_code != 200:
        return
    data = resp.json()
    import base64 as b64
    content = b64.b64decode(data["content"])
    full_path = os.path.join(local_dir, file_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(content)


def download_dir(client, repo_name, dir_path, local_dir):
    """递归下载目录"""
    resp = client.session.get(
        client._url(f"/repos/{client.org}/{repo_name}/contents/{dir_path}")
    )
    if resp.status_code != 200:
        return
    for item in resp.json():
        if item["type"] == "file":
            download_file(client, repo_name, item["path"], local_dir)
        elif item["type"] == "dir":
            download_dir(client, repo_name, item["path"], local_dir)


# ──────────────────────────────────────────────
# Push 操作
# ──────────────────────────────────────────────

def push_new_repos(client, remote_repos, local_dir, dry_run=False):
    """将本地新增的文件夹推送到远程"""
    local_dirs = list_local_dirs(local_dir)
    new_dirs = [d for d in local_dirs if d not in remote_repos]

    print(f"{'='*60}")
    print(f"[PUSH] 推送本地新仓库到远程")
    print(f"{'='*60}")
    print(f"本地文件夹: {len(local_dirs)} 个")
    print(f"远程已存在: {len(local_dirs) - len(new_dirs)} 个")
    print(f"待推送:     {len(new_dirs)} 个\n")

    if not new_dirs:
        print("  没有新仓库需要推送\n")
        return

    for i, dir_name in enumerate(new_dirs, 1):
        local_path = os.path.join(local_dir, dir_name)
        files = collect_files(local_path)

        print(f"  [{i}/{len(new_dirs)}] {dir_name} ({len(files)} 个文件)")

        if dry_run:
            for f in files:
                print(f"       - {f}")
            continue

        # 创建远程仓库
        result = client.create_repo(dir_name)
        if result is None:
            print(f"       -> 无权限创建仓库，跳过")
            continue

        # 上传文件
        success, failed = 0, 0
        for rel_path in files:
            abs_path = os.path.join(local_path, rel_path)
            content_b64 = file_to_base64(abs_path)
            try:
                client.upsert_file(dir_name, rel_path, content_b64, f"Add {rel_path}")
                success += 1
            except Exception as e:
                print(f"       FAILED: {rel_path} - {e}")
                failed += 1

        print(f"       -> {success}/{len(files)} 文件已上传, {failed} 失败")

    print()


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Gitea 组织仓库双向同步（先拉取远程，再推送本地新增）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 完整同步（先 pull 再 push）
  python pull_push_gitea.py --token TOKEN --local-dir ./skills

  # 仅预览
  python pull_push_gitea.py --token TOKEN --local-dir ./skills --dry-run

  # 仅拉取
  python pull_push_gitea.py --token TOKEN --local-dir ./skills --pull-only

  # 仅推送
  python pull_push_gitea.py --token TOKEN --local-dir ./skills --push-only
        """,
    )
    parser.add_argument("--token", required=True, help="Gitea API Token")
    parser.add_argument("--local-dir", required=True, help="本地同步目录")
    parser.add_argument("--gitea-url", default=DEFAULT_CONFIG["gitea_url"], help="Gitea 地址")
    parser.add_argument("--org", default=DEFAULT_CONFIG["org"], help="组织名")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不执行操作")
    parser.add_argument("--pull-only", action="store_true", help="仅拉取远程仓库")
    parser.add_argument("--push-only", action="store_true", help="仅推送本地新仓库")
    args = parser.parse_args()

    client = GiteaClient(args.gitea_url, args.token, args.org, verify=DEFAULT_CONFIG["ssl_verify"])

    # 验证连接
    try:
        user = client.get_current_user()
        username = user["login"]
    except Exception as e:
        print(f"错误: 无法连接 Gitea - {e}")
        sys.exit(1)

    # 获取远程仓库列表
    try:
        remote_repos = client.list_repos()
    except Exception as e:
        print(f"错误: 无法获取远程仓库列表 - {e}")
        sys.exit(1)

    print(f"Gitea:   {args.gitea_url}")
    print(f"组织:    {args.org}")
    print(f"用户:    {username}")
    print(f"本地:    {args.local_dir}")
    print(f"远程仓库: {len(remote_repos)} 个")
    if args.dry_run:
        print("模式:    DRY-RUN（仅预览）")
    print()

    os.makedirs(args.local_dir, exist_ok=True)

    # Step 1: 拉取
    if not args.push_only:
        pull_repos(client, remote_repos, args.local_dir, dry_run=args.dry_run)

    # Step 2: 推送
    if not args.pull_only:
        push_new_repos(client, remote_repos, args.local_dir, dry_run=args.dry_run)

    print(f"{'='*60}")
    print("同步完成")


if __name__ == "__main__":
    main()
