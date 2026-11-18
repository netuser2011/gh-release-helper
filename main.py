#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Release 交互式下载助手 —— 主菜单入口。

    python main.py                 进入交互菜单
    python main.py files-community/Files   直接跳到该仓库的 Release
    python main.py files           先搜索再选编号

菜单四项：1 搜索仓库 / 2 查看收藏 / 3 添加收藏 / 4 退出。
"""

from __future__ import annotations

import os
import sys

# 运行环境检查放在所有业务模块之前：Python 太老、requests 没装，都要给出看得懂、
# 且不会随窗口一起消失的提示（细节见 bootstrap.py）。
import bootstrap

bootstrap.ensure_runtime()

import argparse
from pathlib import Path

import downloader as dl
import favorites as fav
import github_api as gh
import syscert
import ui

# 类型选择时优先给出的两种格式（其余按资产里实际出现的扩展名动态补上）
PREFERRED_TYPES = ["zip", "exe"]
DESC_WIDTH = 40

# Token 来源，仅用于主界面提示
token_source = ""


def pick_token(cli_token: str) -> tuple[str, str]:
    """确定本次使用的 Token 及其来源，Token 一律来自外部，不写进源码。"""
    if cli_token:
        return cli_token.strip(), "--token 参数"
    env = os.environ.get("GITHUB_TOKEN", "").strip()
    if env:
        return env, "环境变量"
    from_file = gh.resolve_token()
    if from_file:
        return from_file, "本地 .github_token"
    return "", ""


def token_state(token: str) -> str:
    if not token:
        return ui.c("未配置（限流 60 次/小时）· 按 0 配一个", ui.RED)
    return ui.c(f"已配置 · {token_source}", ui.GREEN)


def configure_token() -> str:
    """打开 GitHub 的 Token 生成页，用户粘回来只写进本地 .github_token。

    菜单里的 0 和首次启动的引导都走这里：链接由代码打印、交给系统浏览器打开，
    Token 本身永远来自用户输入，不进源码、不进命令行历史以外的地方。
    """
    print()
    print(ui.c("  GitHub Token 生成页（公共仓库只需要 public_repo 一项）：", ui.CYAN))
    print(f"  {ui.c(gh.TOKEN_CREATE_URL, ui.BOLD)}")
    print(ui.c(f"  想用细粒度 Token：{gh.FINE_GRAINED_URL}", ui.GREY))
    print(ui.c(f"  查看/撤销已发的 Token：{gh.TOKENS_PAGE_URL}", ui.GREY))
    if ui.confirm("  现在用系统默认浏览器打开这个页面吗？", default=True):
        if dl.open_in_browser(gh.TOKEN_CREATE_URL):
            print(ui.c("  ✔ 已交给浏览器。创建后把页面顶部那串以 ghp_ 开头的字符粘回来。", ui.GREEN))
        else:
            print(ui.c("  ⚠ 没能自动打开浏览器，手动复制上面第一行地址即可。", ui.YELLOW))
    raw = ui.ask("  粘贴 Token（直接回车放弃）：")
    if not raw:
        print(ui.c("  已取消，继续匿名使用（限流 60 次/小时）。", ui.GREY))
        return ""
    path = gh.save_token(raw)
    print(ui.c(f"  ✔ 已保存到 {path}（已在 .gitignore 中忽略，不会被提交）。", ui.GREEN))
    return raw


def offer_token_setup() -> str:
    """首次运行且没有 Token 时，先问一句，再把页面和粘贴交给 configure_token。"""
    if not ui.is_tty():
        return ""
    print()
    if not ui.confirm("未检测到 GitHub Token（匿名限流 60 次/小时），现在配置一个吗？", default=False):
        print(ui.c("  好的，跳过。之后可在菜单里按 0，或把 Token 写入 .github_token / 环境变量 GITHUB_TOKEN。", ui.GREY))
        return ""
    return configure_token()


# ---------- 通用小流程 ----------


def prompt_keyword(tip: str) -> str | None:
    keyword = ui.ask(ui.c(f"  {tip}", ui.CYAN))
    return keyword or None


def search_and_pick(keyword: str, token: str) -> dict | None:
    """搜索仓库并让用户按编号选一个，返回选中那条 API 数据。"""
    print(ui.c(f'\n  🔎 正在搜索仓库名包含 "{keyword}" 的项目 ...', ui.DIM), flush=True)
    items, total = gh.search_repos(keyword, token, limit=10)
    if not items:
        print(ui.c(f"  ⚠ 没有找到名字包含 \"{keyword}\" 的仓库，换个关键词试试。", ui.YELLOW))
        return None

    print(ui.c(f'\n  搜索 "{keyword}" 命中 {total} 个仓库，按星标排序列出前 {len(items)} 个：\n', ui.BOLD))
    rows = []
    for i, item in enumerate(items, 1):
        rows.append(
            [
                str(i),
                item.get("full_name", "(未知)"),
                format_stars(int(item.get("stargazers_count", 0) or 0)),
                item.get("language") or "-",
                ui.truncate(item.get("description") or "", DESC_WIDTH),
            ]
        )
    ui.table(rows, ["#", "仓库（作者/名字）", "星标", "语言", "简介"])

    num = ui.choose("  请输入编号选择仓库：", len(items), allow_zero=True)
    if not num:
        return None
    chosen = items[num - 1]
    print(ui.c(f"\n  ✔ 已选择：{chosen.get('full_name')}（⭐ {format_stars(int(chosen.get('stargazers_count', 0) or 0))}）", ui.GREEN))
    return chosen


def format_stars(num: int) -> str:
    return f"{num / 1000:.1f}k" if num >= 1000 else str(num)


def type_options(assets: list[dict]) -> list[tuple[str, str]]:
    """根据实际资产生成类型菜单：ZIP / EXE 永远排在最前，其余按出现频次补上。"""
    counts: dict[str, int] = {}
    for a in assets:
        ext = gh.asset_ext(a.get("name", ""))
        counts[ext] = counts.get(ext, 0) + 1
    ordered = [e for e in PREFERRED_TYPES if e in counts]
    ordered += sorted((e for e in counts if e not in PREFERRED_TYPES), key=lambda e: (-counts[e], e))
    return [(e.upper(), e) for e in ordered]


def asset_table(assets: list[dict], offset: int = 1) -> None:
    rows = []
    for i, a in enumerate(assets, offset):
        rows.append(
            [
                str(i),
                ui.truncate(a.get("name", "(未命名)"), 52),
                ui.human_size(int(a.get("size", 0) or 0)),
                gh.asset_ext(a.get("name", "")),
            ]
        )
    ui.table(rows, ["#", "文件名", "大小", "类型"])


def choose_type(assets: list[dict]) -> list[dict]:
    """先问 ZIP 还是 EXE（也支持其它类型与全部），返回筛选后的资产。"""
    options = type_options(assets)
    if not options:
        return []
    if len(options) == 1:
        only = options[0][0]
        print(ui.c(f"  该 release 的资产全部是 {only}，共 {len(assets)} 个。", ui.DIM))
        return assets

    parts = [ui.c(f"{i}. {label}", ui.CYAN) for i, (label, _) in enumerate(options, 1)]
    parts.append(ui.c(f"{len(options) + 1}. 全部", ui.GREY))
    print("  请选择文件类型：" + "   ".join(parts))
    num = ui.choose("  输入类型编号：", len(options) + 1, allow_zero=True)
    if not num:
        return []
    if num == len(options) + 1:
        return assets
    ext = options[num - 1][1]
    picked = gh.filter_by_ext(assets, [ext])
    print(ui.c(f"  已按 {ext.upper()} 筛选出 {len(picked)} 个文件。", ui.DIM))
    return picked


def normalize_dir(raw: str) -> Path:
    """展开 ~ 并把相对路径按当前工作目录解析成绝对路径。"""
    target = Path(raw).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    return target.resolve()


def choose_destination() -> Path | None:
    """下载前让用户选目录：用默认目录、仅本次换目录、换目录并永久记住、恢复系统默认。"""
    current = dl.resolve_download_dir()
    saved = bool(str(dl.load_config().get("download_dir", "")).strip())
    print()
    print("  下载到哪里？")
    print("   " + ui.c(f"1. 当前默认目录：{current}", ui.CYAN))
    print("   " + ui.c("2. 换一个位置（仅本次）", ui.CYAN))
    print("   " + ui.c("3. 换一个位置并记住（设为新的默认目录）", ui.CYAN))
    if saved:
        print("   " + ui.c("4. 恢复系统默认下载目录", ui.GREY))
    hi = 4 if saved else 3
    num = ui.choose("  请选择：", hi, allow_zero=True)
    if not num:
        return None
    if num == 1:
        return dl.download_dir()
    if num == 4 and saved:
        dl.clear_default_download_dir()
        print(ui.c(f"  ✔ 已恢复系统默认下载目录：{dl.system_download_dir()}", ui.GREEN))
        return dl.download_dir()

    raw = ui.ask("  输入目录路径（支持 ~ 与相对路径，回车放弃）：")
    if not raw:
        return None
    target = normalize_dir(raw)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(ui.c(f"  ✖ 无法创建目录 {target}：{exc}", ui.RED))
        print(ui.c("     已改用当前默认目录。", ui.DIM))
        return dl.download_dir()
    if num == 3:
        dl.set_default_download_dir(target)
        print(ui.c(f"  ✔ 已记住，以后默认下载到：{target}", ui.GREEN))
    else:
        print(ui.c(f"  本次下载到：{target}", ui.DIM))
    return target


def route_choices() -> list[tuple[str, str]]:
    """线路菜单：第一项永远是自动测速，后面按白名单顺序把每条线路摆出来。"""
    return [("自动测速，挑最快的一条", dl.AUTO_ROUTE)] + [(item["label"], item["id"]) for item in dl.MIRRORS]


def choose_route() -> str | None:
    """问一句走哪条线路，返回线路 id；返回 0 或取消时给 None。"""
    choices = route_choices()
    print()
    print("  用哪条线路？")
    for index, (label, _) in enumerate(choices, start=1):
        tail = ui.c("（推荐）", ui.GREY) if index == 1 else ""
        print(f"   {ui.c(f'{index}.', ui.CYAN)} {ui.c(label, ui.CYAN)}{tail}")
    num = ui.choose("  请选择：", len(choices), allow_zero=True)
    if not num:
        return None
    return choices[num - 1][1]


def report_speedtest(results: list[dict], chosen: dict) -> None:
    """把测速明细摆成表：快的排上面，不通的排下面并写清原因。"""
    print(ui.c(f"  线路测速（{len(results)} 条并发，每条只拉前 {ui.human_size(dl.PROBE_BYTES)}）：", ui.CYAN))
    ordered = sorted(results, key=lambda item: (not item.get("ok"), -item.get("speed", 0.0)))
    rows = []
    for item in ordered:
        if item["id"] == chosen.get("id"):
            note = "◀ 已选中"
        else:
            note = ui.truncate(item.get("error", ""), 22)
        rows.append([
            item["label"],
            f"{item['latency'] * 1000:.0f} ms" if item.get("ok") else "-",
            f"{item['speed'] / 1024:.0f} KB/s" if item.get("ok") else "不通",
            note,
        ])
    ui.table(rows, ["线路", "首字节", "吞吐", "备注"])


def do_download(repo: str, asset: dict) -> None:
    """三种方式各走各的路：终端下载 / 浏览器下载 / 只给链接。

    第一版把「唤起浏览器 + 本地下载」合成了一项，同一个文件下两遍，
    被 issue 指出成事不足败事有余——现在一项只做一件事。
    """
    url = asset.get("browser_download_url", "")
    name = asset.get("name", "release-asset")
    if not url:
        print(ui.c("  ⚠ 这个资产没有可用的下载地址。", ui.YELLOW))
        return

    print()
    print("  怎么下载？")
    print("   " + ui.c("1. 终端下载到本地", ui.CYAN) + ui.c("（多线程分段 + 镜像测速）", ui.GREY))
    print("   " + ui.c("2. 唤起浏览器下载", ui.CYAN))
    print("   " + ui.c("3. 只打印下载链接", ui.CYAN) + ui.c("（自己粘到浏览器或其它下载工具）", ui.GREY))
    num = ui.choose("  请选择：", 3, allow_zero=True)
    if not num:
        return

    if num == 3:
        print(ui.c(f"\n  {repo}  ·  {name}\n  {url}\n", ui.GREEN))
        print(ui.c("  复制上面这行链接即可，不用再回到本工具。", ui.DIM))
        return

    if num == 2:
        if dl.open_in_browser(url):
            print(ui.c("  🌐 已调用系统默认浏览器打开下载。", ui.GREEN))
        else:
            print(ui.c(f"  ⚠ 没能自动唤起浏览器，请手动打开：\n     {url}", ui.YELLOW))
        return

    mirror = choose_route()
    if not mirror:
        return
    target_dir = choose_destination()
    if not target_dir:
        return

    try:
        line, results = dl.choose_line(url, mirror)
    except dl.DownloadError as exc:
        print(ui.c(f"  ✖ {exc}", ui.RED))
        return
    if results:
        report_speedtest(results, line)

    label = f"{line['label']} · {ui.human_size(asset.get('size') or 0)}" if asset.get("size") else line["label"]
    print(ui.c(f"  ⬇ 线路：{label}   正在下载到 {target_dir} ...", ui.DIM))
    try:
        saved, how = dl.fetch(line["url"], name, target_dir)
    except dl.DownloadError as exc:
        print(ui.c(f"  ✖ {exc}", ui.RED))
        print(ui.c("     可以换一条线路或改用浏览器方式重试。", ui.DIM))
        return
    print(ui.c(f"  ✔ 下载完成：{saved}（{ui.human_size(saved.stat().st_size)} · {how}）", ui.GREEN))


def browser_targets(repo: str, release: dict | None = None, chosen: dict | None = None) -> list[tuple[str, str]]:
    """收集这个仓库能跳的网页：Release 发布页、GitHub 主页、作者填的项目官网。"""
    links: list[tuple[str, str]] = []
    if release:
        page = (release.get("html_url") or "").strip()
        if page:
            links.append(("Release 发布页", page))
    links.append(("GitHub 仓库主页", f"https://github.com/{repo}"))
    homepage = ((chosen or {}).get("homepage") or "").strip()
    if homepage:
        if "://" not in homepage:
            homepage = "https://" + homepage
        links.append(("项目官网", homepage))
    return links


def offer_browser(links: list[tuple[str, str]]) -> None:
    """列出可跳转的网页，让用户选一个交给系统浏览器。"""
    if not links:
        return
    print(ui.c("\n  可以打开这些页面：", ui.BOLD))
    for i, (label, _) in enumerate(links, 1):
        print(f"   {ui.c(str(i), ui.CYAN)}. {label}")
    num = ui.choose("  请选择（0 返回）：", len(links), allow_zero=True)
    if not num:
        return
    label, url = links[num - 1]
    if dl.open_in_browser(url):
        print(ui.c(f"  🌐 已在浏览器打开：{label}", ui.GREEN))
    else:
        print(ui.c(f"  ⚠ 没能自动打开，请手动复制：{url}", ui.YELLOW))


def offer_repo_gateway(repo: str, chosen: dict) -> bool:
    """搜索选中仓库后的岔路口：直接看 Release 下载，还是先去网页看看。

    返回 True 表示继续走下载流程；选了网页或返回则结束本次流程。
    """
    links = browser_targets(repo, chosen=chosen)
    if not links:
        return True
    print(ui.c(f"\n  已选择 {repo}，接下来？", ui.BOLD))
    print("   " + ui.c("1. 查看 Release 资产并下载（推荐）", ui.CYAN))
    for i, (label, _) in enumerate(links, 2):
        print("   " + ui.c(f"{i}. 打开{label}", ui.CYAN))
    num = ui.choose("  请选择（0 返回）：", len(links) + 1, allow_zero=True)
    if not num:
        return False
    if num == 1:
        return True
    label, url = links[num - 2]
    if dl.open_in_browser(url):
        print(ui.c(f"  🌐 已在浏览器打开：{label}", ui.GREEN))
    else:
        print(ui.c(f"  ⚠ 没能自动打开，请手动复制：{url}", ui.YELLOW))
    return False


def browse_release(repo: str, token: str, store: dict | None = None, fav_key: str = "",
                   repo_meta: dict | None = None) -> None:
    """展示某个仓库最新 release 的资产，并进入「选文件 → 选类型 → 下载」流程。"""
    print(ui.c(f"\n  ⏳ 正在获取 {repo} 的最新 release ...", ui.DIM), flush=True)
    release = gh.get_latest_release_or_explain(repo, token)
    tag = release.get("tag_name") or "(无 tag)"
    title = f"{repo}  ·  {tag}"
    name = release.get("name") or ""
    print()
    ui.banner(title, name if name and name != tag else "")

    assets = gh.release_assets(release)
    if not assets:
        print(ui.c("  该 release 没有上传任何资产文件（作者可能把安装包放在了自己的官网）。", ui.YELLOW))
        # 没资产不等于没出路：把发布页、仓库主页、作者官网摆出来让用户跳过去找
        offer_browser(browser_targets(repo, release=release, chosen=repo_meta))
        return

    print(ui.c(f"  共 {len(assets)} 个资产：\n", ui.BOLD))
    asset_table(assets)
    if store is not None and fav_key:
        cache = [
            {"name": a.get("name", ""), "size": int(a.get("size", 0) or 0), "url": a.get("browser_download_url", "")}
            for a in assets
        ]
        fav.update_release(store, fav_key, tag, cache)
        fav.save(store)

    picked = choose_type(assets)
    if not picked:
        return
    if len(picked) > 1:
        print(ui.c("\n  符合该类型的文件：\n", ui.BOLD))
        asset_table(picked)
        num = ui.choose("  请输入要下载的文件编号：", len(picked), allow_zero=True)
        if not num:
            return
        asset = picked[num - 1]
    else:
        asset = picked[0]
        print(ui.c(f"  只有 1 个匹配文件：{asset.get('name')}", ui.DIM))

    do_download(repo, asset)

    # 搜索结果里的仓库顺手问一句要不要收藏，省得再走一遍菜单
    if store is not None and not fav_key and not fav.find_key(store, repo):
        if ui.confirm("\n  要把这个仓库加入收藏吗？", default=False):
            key, action = fav.add(store, repo)
            fav.save(store)
            print(ui.c(f"  ✔ 已{action}收藏：{key}", ui.GREEN))


# ---------- 四大菜单流程 ----------


def flow_search(store: dict, token: str) -> None:
    """1 搜索仓库：关键词 → 编号 → 展示 Release 资产 → 下载。"""
    keyword = prompt_keyword("请输入仓库名关键词：")
    if not keyword:
        return
    chosen = search_and_pick(keyword, token)
    if not chosen:
        return
    full = chosen.get("full_name", "")
    if not offer_repo_gateway(full, chosen):
        return
    browse_release(full, token, store, repo_meta=chosen)


def flow_favorites(store: dict, token: str) -> None:
    """2 查看收藏：按编号选一个，直接调出它的 Release 资产。"""
    items = fav.entries(store)
    if not items:
        print(ui.c("\n  收藏夹还是空的，先用菜单 3 添加一个常用仓库吧。", ui.YELLOW))
        return

    print(ui.c(f"\n  ⭐ 我的收藏（共 {len(items)} 个）：\n", ui.BOLD))
    rows = []
    for i, (key, meta) in enumerate(items, 1):
        rows.append(
            [
                str(i),
                key,
                format_stars(int(meta.get("stars", 0) or 0)),
                meta.get("last_tag") or "未获取",
                ui.c(f"{len(meta.get('assets') or [])} 个", ui.DIM) if meta.get("assets") else ui.c("-", ui.DIM),
                ui.truncate(meta.get("description") or "", DESC_WIDTH),
            ]
        )
    ui.table(rows, ["#", "仓库（作者/名字）", "星标", "最新 tag", "缓存资产", "简介"])

    num = ui.choose("  请输入编号调出下载链接：", len(items), allow_zero=True)
    if not num:
        return
    key, meta = items[num - 1]

    print(ui.c("\n  对这个收藏想做什么？", ui.BOLD))
    print("   " + ui.c("1. 获取最新 Release 资产并下载（推荐）", ui.CYAN))
    print("   " + ui.c("2. 使用上次缓存的资产清单（不联网，可能已过期）", ui.CYAN))
    print("   " + ui.c("3. 取消收藏", ui.CYAN))
    action = ui.choose("  请选择：", 3, allow_zero=True)
    if not action:
        return
    if action == 3:
        if ui.confirm(f"  确认取消收藏 {key}？", default=False):
            removed = fav.remove(store, key)
            fav.save(store)
            print(ui.c(f"  ✔ 已移除：{removed}", ui.GREEN))
        return
    if action == 2:
        cached = meta.get("assets") or []
        if not cached:
            print(ui.c("  ⚠ 这条收藏还没有资产缓存，请先选 1 联网获取一次。", ui.YELLOW))
            return
        print(ui.c(f"  📦 上次记录：{meta.get('last_tag') or '未知 tag'}，共 {len(cached)} 个资产\n", ui.DIM))
        asset_table([{"name": a.get("name", ""), "size": a.get("size", 0), "browser_download_url": a.get("url", "")} for a in cached])
        num2 = ui.choose("  请输入编号选择文件：", len(cached), allow_zero=True)
        if num2:
            do_download(key, {"name": cached[num2 - 1].get("name", ""), "browser_download_url": cached[num2 - 1].get("url", "")})
        return
    browse_release(key, token, store, fav_key=key)


def flow_add_favorite(store: dict, token: str) -> None:
    """3 添加收藏：关键词 → 编号 → 以「作者名/仓库名」为键写入 JSON。"""
    keyword = prompt_keyword("请输入要收藏的仓库名关键词：")
    if not keyword:
        return
    chosen = search_and_pick(keyword, token)
    if not chosen:
        return
    full = chosen.get("full_name", "")
    key, action = fav.add(
        store,
        full,
        stars=int(chosen.get("stargazers_count", 0) or 0),
        description=chosen.get("description") or "",
        language=chosen.get("language") or "",
    )
    fav.save(store)
    print(ui.c(f"  ✔ 已{action}收藏：{key} → {fav.FAVORITES_FILE.name}", ui.GREEN))
    if ui.confirm("  现在就看它的 Release 下载链接吗？", default=True):
        browse_release(key, token, store, fav_key=key, repo_meta=chosen)


# ---------- 主循环 ----------


MENU_ITEMS = [
    ("1", "搜索仓库", "按名字找项目，选编号看 Release 资产并下载"),
    ("2", "查看收藏", "调出已存仓库的下载链接，支持直接下载"),
    ("3", "添加收藏", "把常用仓库存进 favorites.json"),
    ("4", "退出", "保存收藏并退出"),
]

# 四大流程之外的辅助项：不占编号 1-4，也不参与 dispatch()
SUPPORT_ITEMS = [
    ("0", "配置 Token", "打开 GitHub Token 页面，粘贴后存本地 .github_token，解除限流"),
]


def render_menu(store: dict, token: str, notice: str = "") -> None:
    """画主菜单：1-4 是四大流程，0 是辅助的 Token 配置。

    notice 是上一条错误/提示，清屏后原样贴回，避免报错一闪而过。
    """
    ui.clear()
    if notice:
        print(notice)
        print()
    ui.banner("GitHub Release 交互式下载助手", "搜索 · 收藏 · 一键下载")
    print(f"  {ui.c('收藏夹', ui.DIM)} {fav.count(store)} 个   "
          f"{ui.c('Token', ui.DIM)} {token_state(token)}   "
          f"{ui.c('下载目录', ui.DIM)} {ui.truncate(str(dl.resolve_download_dir()), 34)}")
    print(f"  {ui.c('证书', ui.DIM)} {syscert.describe()}")
    print()
    for num, label, desc in MENU_ITEMS:
        print(f"   {ui.c(num, ui.YELLOW, ui.BOLD)}  {ui.c(label, ui.BOLD)}{ui.c('  —  ' + desc, ui.GREY)}")
    for num, label, desc in SUPPORT_ITEMS:
        print(f"   {ui.c(num + '  ' + label, ui.DIM)}{ui.c('  —  ' + desc, ui.GREY)}")
    print()


def dispatch(choice: str, store: dict, token: str) -> str:
    """把菜单编号分发到对应流程，返回 exit / pause / again 三种后续动作。

    again 表示「只要重画菜单，不用多按一次回车」；要不要提示、提示什么，
    由主循环决定——因为它手上的 notice 才能在清屏后活下来。
    """
    if choice == "1":
        flow_search(store, token)
    elif choice == "2":
        flow_favorites(store, token)
    elif choice == "3":
        flow_add_favorite(store, token)
    elif choice == "4":
        return "exit"
    else:
        return "again"
    return "pause"


def run_cli_entry(arg: str, token: str) -> int:
    """带参数启动时：直接把用户输入的 owner/repo 或关键词接进同一套交互流程。"""
    store = fav.load()
    try:
        owner, name = gh.normalize_repo(arg)
        if owner:
            browse_release(f"{owner}/{name}", token, store)
        else:
            chosen = search_and_pick(arg, token)
            if chosen:
                full = chosen.get("full_name", "")
                if offer_repo_gateway(full, chosen):
                    browse_release(full, token, store, repo_meta=chosen)
        return 0
    except ui.UserQuit:
        # 命令行模式下按 Ctrl+C / 输入流结束，安静退出，别甩 traceback
        print(ui.c("\n  已取消。", ui.YELLOW))
        fav.save(store)
        return 130
    except (gh.GitHubError, dl.DownloadError) as exc:
        print(ui.c(f"\n  ✖ {exc}", ui.RED), file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GitHub Release 交互式下载助手：搜索仓库、管理收藏、下载 Release 资产",
        epilog="不带参数运行即进入交互菜单。示例：python main.py files-community/Files",
    )
    parser.add_argument("repo", nargs="?", help="owner/repo 或仓库名关键词，直接跳到对应流程")
    parser.add_argument("--token", default="", help="本次运行使用的 GitHub Token（不建议写在代码里）")
    args = parser.parse_args()

    global token_source
    token, token_source = pick_token(args.token)

    if args.repo:
        return run_cli_entry(args.repo, token)

    if not token:
        try:
            token = offer_token_setup()
            if token:
                token_source = "本地 .github_token"
        except ui.UserQuit:
            token = ""

    store = fav.load()
    if store.get("_recovered"):
        print(ui.c("  ⚠ 原 favorites.json 已损坏，已备份为 favorites.json.bak 并重建。", ui.YELLOW))

    try:
        notice = ""
        while True:
            render_menu(store, token, notice)
            notice = ""  # 上一条提示只贴这一次，用户做完下一个动作就该翻篇
            try:
                choice = ui.ask(ui.c("  请输入选项编号 >>> ", ui.MAGENTA))
            except ui.UserQuit:
                # 主菜单处的 Ctrl+C / Ctrl+D 视为退出
                print()
                break
            try:
                if choice == "0":
                    # Token 是运行时才知道的东西，配好之后本次运行立刻换上，不用重启
                    new_token = configure_token()
                    if new_token:
                        token, token_source = new_token, "本地 .github_token"
                        notice = ui.c("  ✔ Token 已生效，限额从 60 次/小时提升到 5000 次/小时。", ui.GREEN)
                    ui.ask(ui.c("\n  回车返回主菜单 ...", ui.GREY))
                else:
                    action = dispatch(choice, store, token)
                    if action == "exit":
                        break
                    if action == "again":
                        # 重画菜单即可，不用多按一次回车；直接回车不配挨一句"无效选项"
                        if choice:
                            notice = ui.c("  ⚠ 无效选项，请输入 1-4（0 配置 Token）。", ui.YELLOW)
                    elif action == "pause":
                        ui.ask(ui.c("\n  回车返回主菜单 ...", ui.GREY))
            except ui.UserQuit:
                notice = ui.c("  已取消，返回主菜单。", ui.YELLOW)
            except (gh.GitHubError, dl.DownloadError) as exc:
                notice = ui.c(f"  ✖ {exc}", ui.RED)
    finally:
        fav.save(store)

    print(ui.c("\n  👋 收藏已保存，下次见。\n", ui.GREEN))
    return 0


if __name__ == "__main__":
    ui.setup_streams()  # 必须最先执行：GBK 控制台里 print emoji 会直接闪退
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(ui.c("\n\n  已强制退出。\n", ui.YELLOW))
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001  兜底：留下可读的报错，而不是闪退
        ui.report_crash(exc)
        sys.exit(1)
