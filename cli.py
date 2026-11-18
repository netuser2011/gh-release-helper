#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令行模式：一条命令直接打印最新 release 的全部下载链接。

    python cli.py files-community/Files
    python cli.py cli/cli --ext exe msi zip
    python cli.py microsoft/vscode --no-latest --limit 3
    python cli.py --token-url              # 只要 GitHub Token 创建页地址

适合不想进菜单、只想拿到链接的场景；需要搜索、收藏、自动下载请用 python main.py。
"""

from __future__ import annotations

import sys

import bootstrap

bootstrap.ensure_runtime()  # Python 版本与 requests，失败时提示不会随窗口一起消失

import argparse

import github_api as gh
import ui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="打印 GitHub 仓库最新 release 的资产下载链接（基于官方 REST API）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n  python cli.py files-community/Files --ext exe msixbundle zip\n"
               "  python cli.py --token-url        # 只要 Token 创建页地址",
    )
    parser.add_argument("repo", nargs="?", help="仓库名，格式为 owner/repo")
    parser.add_argument("--ext", nargs="+", metavar="EXT", default=[], help="按扩展名筛选，如 --ext exe zip")
    parser.add_argument("--no-latest", dest="latest", action="store_false", help="列出最近的若干条 release")
    parser.add_argument("--limit", type=int, default=5, help="搭配 --no-latest 使用，默认 5 条")
    parser.add_argument("--token", default="", help="本次运行使用的 GitHub Token")
    parser.add_argument("--token-url", dest="token_url", action="store_true",
                        help="打印 GitHub Token 创建页地址后退出，用于解除 API 限流")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.token_url:
        # 给脚本和远程排障用：只输出地址，不读也不写任何 Token
        print(gh.TOKEN_CREATE_URL)
        print(gh.FINE_GRAINED_URL)
        return 0
    if not args.repo:
        print("错误：请给出仓库名（owner/repo），或用 --token-url 只打印 Token 页面地址", file=sys.stderr)
        return 2

    token = args.token or gh.resolve_token()

    owner, name = gh.normalize_repo(args.repo)
    if not owner:
        print(f"错误：仓库名格式不正确 → {args.repo}，应为 owner/repo", file=sys.stderr)
        return 2
    repo = f"{owner}/{name}"

    print(f"正在查询 {repo} 的 {'最新' if args.latest else '最近'} release ...", flush=True)
    try:
        if args.latest:
            releases = [gh.get_latest_release_or_explain(repo, token)]
        else:
            releases = gh.list_releases(repo, token, args.limit)
    except gh.GitHubError as exc:
        print(f"\n错误：{exc}", file=sys.stderr)
        return 1

    shown = 0
    for release in releases:
        if not isinstance(release, dict):
            continue
        assets = gh.release_assets(release)
        filtered = gh.filter_by_ext(assets, args.ext)
        tag = release.get("tag_name") or "(无 tag)"
        title = f"{repo}  ·  {tag}"
        print(f"\n{'=' * max(len(title), 20)}\n  {title}\n{'=' * max(len(title), 20)}")

        if not assets:
            print("  该 release 没有任何资产文件。")
            continue
        if not filtered:
            print(f"  该 release 有 {len(assets)} 个资产，但没有匹配 {', '.join(args.ext)} 的文件。")
            continue

        rows = [
            [str(i), a.get("name", "(未命名)"), ui.human_size(int(a.get("size", 0) or 0)), a.get("browser_download_url", "")]
            for i, a in enumerate(filtered, 1)
        ]
        ui.table(rows, ["#", "文件名", "大小", "下载链接"])
        print(f"  共 {len(filtered)} 个文件")
        shown += len(filtered)

    if not shown:
        return 1
    return 0


if __name__ == "__main__":
    ui.setup_streams()  # 必须最先执行：GBK 控制台里 print 中文/特殊字符会直接闪退
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001  兜底：留下可读的报错，而不是闪退
        ui.report_crash(exc)
        sys.exit(1)
