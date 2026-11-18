#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""入口前置检查：Python 版本与第三方依赖。

这个模块有两条例外规矩，别随手改：

1. 只用标准库，且不写 ``from __future__ import annotations``。它是「Python 太老」
   和「requests 没装」这两类问题的报错出口，自己必须先能跑起来。
2. 失败时不能直接 ``sys.exit(消息)``。双击运行时命令行窗口会在打印的同一瞬间关闭，
   用户看到的是「闪退」而不是一句话说明，所以这里坚持打印 + 落盘 + 等按键。
"""

import os
import sys
import time
import traceback

MIN_PYTHON = (3, 8)


def _crash_log_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")


def _append_log(message):
    try:
        with open(_crash_log_path(), "a", encoding="utf-8") as fh:
            fh.write("\n[%s] Python %s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                                 sys.version.split()[0], message))
        return _crash_log_path()
    except OSError:
        return ""


def _wait_for_enter():
    """有人坐在键盘前时才等按键；管道和自动化输入要立刻返回，否则会卡住。"""
    if not (sys.stdin and sys.stdin.isatty()):
        return
    try:
        input("\n按回车键退出 ...")
    except (EOFError, KeyboardInterrupt):
        pass


def fatal_exit(message, err=None, code=1):
    """打印致命错误、写进 crash.log、等用户按键后再退出。"""
    print("\n" + message, file=sys.stderr)
    if err is not None:
        traceback.print_exception(type(err), err, err.__traceback__, file=sys.stderr)
    saved = _append_log(message)
    if saved:
        print("（上面的内容也已写入 %s）" % saved, file=sys.stderr)
    sys.stderr.flush()
    _wait_for_enter()
    raise SystemExit(code)


def ensure_runtime():
    """检查 Python 版本与 requests，通过后把 requests 模块返回给调用方。"""
    if sys.version_info < MIN_PYTHON:
        fatal_exit(
            "需要 Python %d.%d 或更高版本，当前是 %s。\n"
            "升级 Python 后再运行即可，代码本身没有问题。"
            % (MIN_PYTHON[0], MIN_PYTHON[1], sys.version.split()[0])
        )
    try:
        import requests
    except ImportError as err:
        hint = ""
        if getattr(err, "name", None) == "ssl":
            hint = "\n（Python 自带的 OpenSSL / _ssl 没编译好，属于装 Python 时的问题，重装一次官方安装包通常就好。）"
        fatal_exit(
            "缺少第三方依赖 requests，请先执行：pip install -r requirements.txt\n"
            "如果本机装了多个 Python，用这条更稳：python -m pip install requests\n"
            "双击 Run.bat 会在首次运行时自动执行上面这条；手动运行请先确认它装成功了。" + hint,
            err,
        )
    # 让 requests 信任系统证书：Watt Toolkit 等代理工具的根证书装在系统里，
    # certifi 不认会报 SSL 错误。导出失败也不影响运行，所以放在这里顺带做。
    try:
        import syscert

        syscert.ensure_system_certs()
    except Exception:  # noqa: BLE001  证书是增强项，任何意外都不能挡住启动
        pass
    return requests
