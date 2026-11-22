#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用交互流程：Token 解析、配置向导、首次启动引导。

从 main.py 迁出，核心逻辑留在这里；main.py 通过 import 重新导出同名符号，
保证现有测试里 patch(app.configure_token) 等写法继续生效。
"""

import os

import downloader as dl
import github_api as gh
import ui


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
        print(ui.c("  好的，跳过。之后可在菜单里按 0，或把 Token 写入 .github_token / 环境变量 GITHUB_TOKEN。", ui.GREY))
        return ""
    return (configure or configure_token)()
