#!/usr/bin/env python3
"""
清空 Gitea 组织下的所有仓库

功能：
  - 列出组织下所有仓库
  - 逐个删除仓库（需二次确认）
  - 支持 dry-run 模式预览

用法：
  python cleanup_gitea.py --token TOKEN --dry-run        # 预览将删除的仓库
  python cleanup_gitea.py --token TOKEN                  # 交互式逐个确认删除
  python cleanup_gitea.py --token TOKEN --force           # 跳过确认，删除所有仓库
  python cleanup_gitea.py --token TOKEN --repos repo1,repo2  # 只删除指定仓库
"""

import argparse
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
}


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

    def list_repos(self):
        """列出组织下所有仓库"""
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
        return repos

    def delete_repo(self, repo_name):
        """删除仓库"""
        resp = self.session.delete(self._url(f"/repos/{self.org}/{repo_name}"))
        return resp.status_code == 204


def main():
    parser = argparse.ArgumentParser(
        description="清空 Gitea 组织下的仓库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 预览
  python cleanup_gitea.py --token TOKEN --dry-run

  # 交互式确认删除
  python cleanup_gitea.py --token TOKEN

  # 删除指定仓库
  python cleanup_gitea.py --token TOKEN --repos skill-creator,application-notes

  # 强制删除所有（危险！）
  python cleanup_gitea.py --token TOKEN --force
        """,
    )
    parser.add_argument("--token", required=True, help="Gitea API Token（需组织管理权限）")
    parser.add_argument("--gitea-url", default=DEFAULT_CONFIG["gitea_url"], help="Gitea 地址")
    parser.add_argument("--org", default=DEFAULT_CONFIG["org"], help="组织名")
    parser.add_argument("--repos", default=None, help="只删除指定仓库，逗号分隔（如 repo1,repo2）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不删除")
    parser.add_argument("--force", action="store_true", help="跳过确认提示，直接删除")
    args = parser.parse_args()

    client = GiteaClient(args.gitea_url, args.token, args.org, verify=DEFAULT_CONFIG["ssl_verify"])

    # 获取仓库列表
    try:
        all_repos = client.list_repos()
    except Exception as e:
        print(f"错误: 无法获取仓库列表 - {e}")
        sys.exit(1)

    if not all_repos:
        print(f"组织 {args.org} 下没有仓库")
        return

    # 过滤目标仓库
    if args.repos:
        target_names = set(args.repos.split(","))
        repos = [r for r in all_repos if r["name"] in target_names]
        not_found = target_names - {r["name"] for r in repos}
        if not_found:
            print(f"警告: 以下仓库不存在: {', '.join(not_found)}")
    else:
        repos = all_repos

    # 显示仓库列表
    print(f"组织: {args.org}")
    print(f"{'='*60}")
    print(f"共 {len(repos)} 个仓库:\n")
    for i, repo in enumerate(repos, 1):
        size_kb = repo.get("size", 0) * 1024
        if size_kb > 1024 * 1024:
            size_str = f"{size_kb / 1024 / 1024:.1f} MB"
        elif size_kb > 1024:
            size_str = f"{size_kb / 1024:.1f} KB"
        else:
            size_str = f"{size_kb} B"
        print(f"  {i:3d}. {repo['name']:<35s} {size_str:>10s}  {'私有' if repo.get('private') else '公开'}")
    print()

    # Dry-run 模式
    if args.dry_run:
        print(f"[DRY-RUN] 以上 {len(repos)} 个仓库将被删除")
        return

    # 确认
    if not args.force:
        print(f"!!! 即将删除 {len(repos)} 个仓库，此操作不可恢复 !!!")
        confirm = input("确认删除？输入 'yes' 继续: ").strip()
        if confirm != "yes":
            print("已取消")
            return
        print()

    # 执行删除
    success, failed = 0, 0
    for repo in repos:
        if not args.force:
            ans = input(f"删除 {repo['name']}？[y/N] ").strip().lower()
            if ans != "y":
                print(f"  跳过 {repo['name']}")
                continue

        if client.delete_repo(repo["name"]):
            print(f"  [OK] {repo['name']} 已删除")
            success += 1
        else:
            print(f"  [FAIL] {repo['name']} 删除失败")
            failed += 1

    print(f"\n{'='*60}")
    print(f"完成: {success} 删除成功, {failed} 失败")


if __name__ == "__main__":
    main()
