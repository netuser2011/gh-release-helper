#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用交互流程：Token 解析、配置向导、首次启动引导。

从 main.py 迁出，核心逻辑留在这里；main.py 通过 import 重新导出同名符号，
保证现有测试里 patch(app.configure_token) 等写法继续生效。
"""

import os
import time

import downloader as dl
import github_api as gh
import ui


CHECK_LIMIT_NO_TOKEN = 40  # 匿名只有 60 次/小时，留一半余量给搜索和下载
CONFIRM_ABOVE = 30


def plan_favorite_check(entries: list[tuple[str, dict]], token: str) -> tuple[list, str, str]:
    """批量检查收藏前的裁剪规则，CLI 菜单与 TUI 共用同一套判定。

    返回 (targets, action, notice)，action 三选一：
    - refuse：未配 Token 且超过 CHECK_LIMIT_NO_TOKEN 个，targets 为空，一个请求都不该发；
    - confirm：超过 CONFIRM_ABOVE 个，调用方先问一句——答应就全查，不答应只查前 30 个；
    - run：直接查 targets。
    notice 是给用户看的那句话（含「按 5 配 Token」这种两套界面都成立的键位）。
    """
    total = len(entries)
    if not token and total > CHECK_LIMIT_NO_TOKEN:
        return [], "refuse", (
            f"未配置 Token 时最多检查 {CHECK_LIMIT_NO_TOKEN} 个（共 {total} 个），"
            f"按 5 配置 Token 后重试。")
    if total > CONFIRM_ABOVE:
        return list(entries), "confirm", f"共 {total} 个仓库，全部检查？"
    return list(entries), "run", ""


def iter_favorite_repos(targets: list[tuple[str, dict]], token: str):
    """收藏批量检查更新的限流循环：CLI 菜单与 TUI 共用，两条路径同一套保护。

    规则：目标裁剪由 plan_favorite_check 在调用前决定（拒绝或确认都在那儿）；进入循环前
    查一次剩余配额（/rate_limit 不计费），之后本地递减、不再逐个请求；
    每个请求之间间隔 0.5 秒；403/429 立即停批。

    产出 (index, key, meta, release, exc, stop)：
    - 正常：release 是 release 字典，exc 为 None，stop 为空串；
    - 单仓失败：exc 是异常，release 为 None，stop 为空串（继续下一个）；
    - 停批：stop 是 "insufficient-quota" 或 "rate-limited"，此后不再产出。
    """
    limit, remaining = 0, 0
    try:
        quota = gh.rate_limit_status(token)
        limit = int(quota.get("limit", 0) or 0)
        remaining = int(quota.get("remaining", 0) or 0)
    except gh.GitHubError:
        pass  # 预检失败就跳过本地递减保护，不让增强项挡住主流程

    for index, (key, meta) in enumerate(targets):
        if index:
            time.sleep(0.5)
        if limit > 0 and remaining < 3:
            yield index, key, meta, None, None, "insufficient-quota"
            return
        try:
            release = gh.get_latest_release_or_explain(key, token)
            remaining -= 1
            yield index, key, meta, release, None, ""
        except gh.GitHubError as exc:
            # 404 会多打一次 /repos 确认仓库存在，按 2 次扣
            remaining -= 2 if getattr(exc, "status_code", None) == 404 else 1
            if isinstance(exc, gh.RateLimitedError) or exc.status_code in (403, 429):
                yield index, key, meta, None, exc, "rate-limited"
                return
            yield index, key, meta, None, exc, ""


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


def configure_token() -> str:
    """打开 GitHub 的 Token 生成页，用户粘回来只写进本地 .github_token。"""
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


def offer_token_setup(configure=None) -> str:
    """首次运行且没有 Token 时先问一句；configure 可注入，便于测试 patch。"""
    if not ui.is_tty():
        return ""
    print()
    if not ui.confirm("未检测到 GitHub Token（匿名限流 60 次/小时），现在配置一个吗？", default=False):
        print(ui.c("  好的，跳过。之后可在菜单里按 5，或把 Token 写入 .github_token / 环境变量 GITHUB_TOKEN。", ui.GREY))
        return ""
    return (configure or configure_token)()
