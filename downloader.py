#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载能力：终端多线程分段下载（线路自动测速）、浏览器唤起、复制链接。"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from pathlib import Path

import requests

import ui

CHUNK = 64 * 1024
DOWNLOAD_DIR_ENV = "GHR_DOWNLOAD_DIR"
# 用户自选的默认下载目录记在这里（个人偏好，已在 .gitignore 中忽略）
CONFIG_FILE = Path(__file__).resolve().with_name("config.json")
# 文件名里不允许出现的字符（Windows 保留字符 + 路径分隔符 + 控制字符）
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# ---------- 线路与镜像 ----------
# 镜像站是写死的白名单，不接受用户临时输入：把下载地址交给任意第三方服务器，
# 等于让对方有机会替换文件内容，这条边界不能开。
#
# 下面每个站点入库前都实测过三件事：能拿到 Release 资产（不是兜底广告页）、
# 认 Range（否则多线程分段自动失效）、以及走的是 https。公共镜像寿命很短，
# 加之前请照 .github/../CONTRIBUTING.md 的清单重测一遍。
MIRRORS = (
    {"id": "direct", "label": "直连 GitHub", "prefix": ""},
    {"id": "ghproxy.net", "label": "ghproxy.net", "prefix": "https://ghproxy.net/"},
    {"id": "gh-proxy.com", "label": "gh-proxy.com", "prefix": "https://gh-proxy.com/"},
    {"id": "ghfast.top", "label": "ghfast.top", "prefix": "https://ghfast.top/"},
    {"id": "gh-proxy.org", "label": "gh-proxy.org", "prefix": "https://gh-proxy.org/"},
    {"id": "gh-proxy.eu.org", "label": "gh-proxy.eu.org", "prefix": "https://gh-proxy.eu.org/"},
    {"id": "ghp.keleyaa.com", "label": "ghp.keleyaa.com", "prefix": "https://ghp.keleyaa.com/"},
)
AUTO_ROUTE = "auto"

# ---------- 多线程与测速参数 ----------
PROBE_BYTES = 128 * 1024           # 测速每条线路只拉这一小段；线路多了以后总流量也得算
PROBE_TIMEOUT = 6                  # 单条线路的测速上限（秒）
PROBE_GRACE = 2                    # 整体等待再多的宽限，超了就把没回来的线路记为超时
RANGE_TIMEOUT = (10, 60)           # 连接超时 / 两次读取之间的空闲上限
PARALLEL_MIN_SIZE = 2 * 1024 * 1024  # 太小的文件分段反而更慢，直接单流
DEFAULT_WORKERS = 4
MAX_WORKERS = 8
WORKERS_ENV = "GHR_THREADS"


class DownloadError(Exception):
    """下载过程中的可预期失败。"""


def load_config() -> dict:
    """读取 config.json；文件缺失或损坏时返回空配置，不影响使用。"""
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_config(config: dict) -> Path:
    tmp = CONFIG_FILE.with_name(CONFIG_FILE.name + ".tmp")
    try:
        tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(CONFIG_FILE)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    return CONFIG_FILE


def set_default_download_dir(path: str | Path) -> Path:
    """把某个目录永久记住为默认下载目录。"""
    config = load_config()
    config["download_dir"] = str(Path(path).expanduser().resolve())
    save_config(config)
    return Path(config["download_dir"])


def clear_default_download_dir() -> None:
    """取消记住的目录，回到系统默认下载目录。"""
    config = load_config()
    if config.pop("download_dir", None) is not None:
        save_config(config)


def system_download_dir() -> Path:
    """系统「下载」目录，取不到时退回用户主目录。"""
    home = Path.home()
    return next((home / d for d in ("Downloads", "下载") if (home / d).is_dir()), home / "Downloads")


def resolve_download_dir() -> Path:
    """算出当前生效的默认下载目录，优先级：环境变量 > config.json > 系统下载目录。

    只做路径计算，不碰文件系统（给界面刷新用）。
    """
    env = os.environ.get(DOWNLOAD_DIR_ENV, "").strip()
    if env:
        return Path(env).expanduser()
    saved = str(load_config().get("download_dir", "")).strip()
    if saved:
        return Path(saved).expanduser()
    return system_download_dir()


def download_dir() -> Path:
    """真正要用来自下载的目录：解析出路径并确保它存在。"""
    target = resolve_download_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DownloadError(f"无法创建下载目录 {target}：{exc}") from exc
    return target


def safe_filename(name: str, fallback: str = "release-asset") -> str:
    """净化资产名：只取最后一段、去掉非法字符，防止 ../ 之类的路径穿越写到目录之外。"""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = _ILLEGAL.sub("", base).strip().strip(".")
    if not base:
        base = fallback
    return base[:150]


def unique_path(directory: Path, filename: str) -> Path:
    """目标文件已存在时自动加 (1)(2) 后缀，不覆盖用户已有文件。"""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for i in range(1, 1000):
        candidate = directory / f"{stem}({i}){suffix}"
        if not candidate.exists():
            return candidate
    raise DownloadError(f"同名文件过多，请手动清理：{filename}")


def open_in_browser(url: str) -> bool:
    """调用系统默认浏览器打开链接；成功与否都返回布尔值，不抛异常打断主流程。"""
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def download(url: str, filename: str = "", directory: Path | None = None) -> Path:
    """流式下载到本地，返回最终文件路径。

    先写 .part 临时文件，校验完再改名；Ctrl+C 或网络中断时把半截文件删掉，
    避免留下一个看起来完整、实际打不开的残文件。
    """
    dest_dir = directory or download_dir()
    dest = unique_path(dest_dir, safe_filename(filename or url.rsplit("/", 1)[-1]))
    part = dest.with_name(dest.name + ".part")

    try:
        with requests.get(url, stream=True, timeout=30) as resp:
            if resp.status_code != 200:
                raise DownloadError(f"下载失败（HTTP {resp.status_code}），请确认链接是否还有效：{url}")
            try:
                total = int(resp.headers.get("Content-Length", 0) or 0)
            except ValueError:
                total = 0
            ctype = resp.headers.get("Content-Type", "")
            # 链接被重定向到 HTML 页面时（资产已删除或需要登录）提前止损
            if total == 0 and "text/html" in ctype:
                raise DownloadError(f"服务器返回的是网页而不是文件，链接可能已失效：{url}")

            written = 0
            started = time.time()
            last_draw = 0.0
            with part.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=CHUNK):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    written += len(chunk)
                    now = time.time()
                    if now - last_draw >= 0.12:  # 限制刷新频率，否则刷屏反而看不清
                        last_draw = now
                        rate = written / max(now - started, 1e-6)
                        if ui.is_tty():
                            print("\r " + ui.progress_line(written, total, rate), end="", flush=True)
        if ui.is_tty():
            print()
    except DownloadError:
        part.unlink(missing_ok=True)
        raise
    except KeyboardInterrupt:
        part.unlink(missing_ok=True)
        print()
        raise DownloadError("已取消下载，临时文件已清理。") from None
    except requests.exceptions.RequestException as exc:
        part.unlink(missing_ok=True)
        raise DownloadError(f"下载中断：{exc}") from exc
    except OSError as exc:
        part.unlink(missing_ok=True)
        raise DownloadError(f"写入文件失败（{dest_dir}）：{exc}") from exc

    if written == 0:
        part.unlink(missing_ok=True)
        raise DownloadError("下载到的文件是空的，链接可能已失效。")
    if total and written != total:
        part.unlink(missing_ok=True)
        raise DownloadError(f"文件不完整（{written}/{total} 字节），已放弃。")

    part.replace(dest)
    return dest


# ---------- 线路测速 ----------


def _brief_error(exc: BaseException) -> str:
    """把 requests 那一长串异常压成一行能看的说明。"""
    text = str(exc).strip() or exc.__class__.__name__
    return re.sub(r"\s+", " ", text)[:120]


def worker_count() -> int:
    """并发连接数：默认 4，可用环境变量 GHR_THREADS 调，超出范围就夹住。"""
    try:
        num = int(os.environ.get(WORKERS_ENV, "").strip())
    except ValueError:
        return DEFAULT_WORKERS
    return max(1, min(num, MAX_WORKERS))


def line_url(url: str, mirror_id: str) -> str:
    """把原始下载地址换成某条线路上的地址。"""
    for item in MIRRORS:
        if item["id"] == mirror_id:
            return f"{item['prefix']}{url}" if item["prefix"] else url
    raise DownloadError(f"未知线路：{mirror_id}")


def lines_for(url: str) -> list[dict]:
    """列出全部可选线路（含各自的实际地址）。"""
    return [{"id": item["id"], "label": item["label"], "url": line_url(url, item["id"])} for item in MIRRORS]


def probe_line(url: str, max_bytes: int = PROBE_BYTES, timeout: int = PROBE_TIMEOUT) -> dict:
    """实测一条线路：只拉前一小段，看首字节延迟和吞吐。测不通不抛异常，原因写在结果里。"""
    started = time.time()
    first_byte = 0.0
    got = 0
    try:
        with requests.get(url, headers={"Range": f"bytes=0-{max_bytes - 1}"},
                          stream=True, timeout=timeout) as resp:
            if resp.status_code not in (200, 206):
                return {"ok": False, "speed": 0.0, "latency": 0.0, "bytes": 0,
                        "error": f"HTTP {resp.status_code}"}
            for chunk in resp.iter_content(chunk_size=CHUNK):
                if not chunk:
                    continue
                if not first_byte:
                    first_byte = time.time() - started
                got += len(chunk)
                if got >= max_bytes or time.time() - started >= timeout:
                    break
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "speed": 0.0, "latency": 0.0, "bytes": 0, "error": _brief_error(exc)}
    except OSError as exc:  # 代理、SSL 库偶尔会抛裸 OSError
        return {"ok": False, "speed": 0.0, "latency": 0.0, "bytes": 0, "error": _brief_error(exc)}

    elapsed = max(time.time() - started, 1e-6)
    if got == 0:
        return {"ok": False, "speed": 0.0, "latency": 0.0, "bytes": 0, "error": "没收到任何字节"}
    return {"ok": True, "speed": got / elapsed, "latency": first_byte or elapsed, "bytes": got, "error": ""}


def probe_lines(url: str, wall_timeout: int = 0) -> list[dict]:
    """并发实测全部线路，顺序与 MIRRORS 一致。

    七条线路要是挨个测，最坏得等 7 × 6 秒，界面像卡死一样；改成一起发，
    整体只等 ``PROBE_TIMEOUT + PROBE_GRACE`` 秒，没回来的线路记成超时，
    剩下的照常参与比较。
    """
    lines = lines_for(url)
    budget = wall_timeout or (PROBE_TIMEOUT + PROBE_GRACE)
    measured = {}
    pool = ThreadPoolExecutor(max_workers=len(lines))
    try:
        futures = {pool.submit(probe_line, item["url"]): item["id"] for item in lines}
        try:
            for future in as_completed(futures, timeout=budget):
                line_id = futures[future]
                try:
                    measured[line_id] = future.result()
                except Exception as exc:  # noqa: BLE001  一条线路的意外异常不能带崩整轮测速
                    measured[line_id] = {"ok": False, "speed": 0.0, "latency": 0.0,
                                         "bytes": 0, "error": _brief_error(exc)}
        except FuturesTimeout:
            pass
    finally:
        # 不能等：没返回的那几条自己在 requests 超时里收尾，界面不该陪着卡住
        pool.shutdown(wait=False)

    results = []
    for item in lines:
        outcome = measured.get(item["id"]) or {
            "ok": False, "speed": 0.0, "latency": 0.0, "bytes": 0,
            "error": f"测速超过 {budget} 秒未返回",
        }
        results.append({**item, **outcome})
    return results


def best_line(results: list[dict]) -> dict | None:
    """从测速明细里挑吞吐最高的一条；一条都不通时返回 None。"""
    passed = [item for item in results if item.get("ok")]
    if not passed:
        return None
    return max(passed, key=lambda item: item["speed"])


def choose_line(url: str, mirror: str = AUTO_ROUTE) -> tuple[dict, list[dict]]:
    """定一条下载线路，返回 (选中的线路, 测速明细)；指定线路时明细为空。"""
    if mirror and mirror != AUTO_ROUTE:
        for item in lines_for(url):
            if item["id"] == mirror:
                return item, []
        raise DownloadError(f"未知线路：{mirror}（可选 {', '.join(m['id'] for m in MIRRORS)} 或 auto）")

    results = probe_lines(url)
    chosen = best_line(results)
    if chosen is None:
        detail = "\n".join(f"       · {item['label']}：{(item['error'] or '不通')[:70]}" for item in results)
        raise DownloadError(
            f"{len(results)} 条线路全都不通：{detail}\n"
            "     可以先改用浏览器方式下载，或检查本机代理 / hosts；"
            "代理工具做 HTTPS 中间人时也长这样。")
    return chosen, results


# ---------- 多线程分段下载 ----------


def line_file_info(url: str) -> tuple[int, bool]:
    """问服务器两件事：文件多大、支不支持 Range。用 ``bytes=0-0`` 只要 1 个字节。"""
    try:
        with requests.get(url, headers={"Range": "bytes=0-0"}, stream=True, timeout=RANGE_TIMEOUT) as resp:
            supports = resp.status_code == 206
            total = 0
            match = re.search(r"/(\d+)\s*$", resp.headers.get("Content-Range", ""))
            if match:
                total = int(match.group(1))
            if not total:
                try:
                    total = int(resp.headers.get("Content-Length", 0) or 0)
                except ValueError:
                    total = 0
            return total, supports
    except requests.exceptions.RequestException as exc:
        raise DownloadError(f"连不上下载地址：{_brief_error(exc)}") from exc


def splits(total: int, workers: int) -> list[tuple[int, int]]:
    """把文件切成 workers 段，返回闭区间 ``[(起, 止), ...]``；余数摊给前面几段。"""
    if total <= 0:
        return []
    workers = max(1, min(workers, total))
    size, extra = divmod(total, workers)
    bounds = []
    start = 0
    for index in range(workers):
        length = size + (1 if index < extra else 0)
        bounds.append((start, start + length - 1))
        start += length
    return bounds


def _fetch_range(url: str, start: int, end: int, part: Path, counter: list, lock) -> int:
    """下载 ``[start, end]`` 这一段，直接写进 .part 对应的偏移。"""
    expected = end - start + 1
    written = 0
    try:
        with requests.get(url, headers={"Range": f"bytes={start}-{end}"},
                          stream=True, timeout=RANGE_TIMEOUT) as resp:
            if resp.status_code != 206:
                raise DownloadError(f"线路中途不支持分段（HTTP {resp.status_code}）")
            with part.open("rb+") as fh:
                fh.seek(start)
                for chunk in resp.iter_content(chunk_size=CHUNK):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    written += len(chunk)
                    with lock:
                        counter[0] += len(chunk)
    except requests.exceptions.RequestException as exc:
        raise DownloadError(f"分段下载中断：{_brief_error(exc)}") from exc
    except OSError as exc:
        raise DownloadError(f"写入文件失败（{part}）：{exc}") from exc
    if written != expected:
        raise DownloadError(f"分段不完整（{written}/{expected} 字节）")
    return written


def download_parallel(url: str, directory: Path, filename: str, total: int, workers: int) -> Path:
    """多线程分段下载：先按总长占好 .part，各线程写各自的偏移，最后校验字节数再改名。

    任何一个分段失败都会整个放弃并删掉 .part——宁可让用户重下一次，
    也不留一个「看着完整其实打不开」的文件。
    """
    dest = unique_path(directory, safe_filename(filename))
    part = dest.with_name(dest.name + ".part")
    bounds = splits(total, workers)
    if not bounds:
        raise DownloadError("文件大小未知，无法分段下载。")
    counter = [0]
    lock = threading.Lock()
    started = time.time()

    try:
        with part.open("wb") as fh:
            fh.truncate(total)
        with ThreadPoolExecutor(max_workers=len(bounds)) as pool:
            futures = [pool.submit(_fetch_range, url, start, end, part, counter, lock)
                       for start, end in bounds]
            while True:
                if ui.is_tty():
                    rate = counter[0] / max(time.time() - started, 1e-6)
                    print("\r " + ui.progress_line(counter[0], total, rate), end="", flush=True)
                if all(future.done() for future in futures):
                    break
                time.sleep(0.12)
            for future in futures:
                future.result()  # 子线程的异常在这里冒出来
        if ui.is_tty():
            print()
    except KeyboardInterrupt:
        part.unlink(missing_ok=True)
        print()
        raise DownloadError("已取消下载，临时文件已清理。") from None
    except DownloadError:
        part.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001  线程池里冒出来的任何异常都不该以 traceback 收场
        part.unlink(missing_ok=True)
        raise DownloadError(f"下载失败：{_brief_error(exc)}") from exc

    if counter[0] != total or part.stat().st_size != total:
        part.unlink(missing_ok=True)
        raise DownloadError(f"文件不完整（{counter[0]}/{total} 字节），已放弃。")

    part.replace(dest)
    return dest


def fetch(url: str, filename: str = "", directory: Path | None = None,
          workers: int | None = None) -> tuple[Path, str]:
    """终端下载入口：能分段又值得分段就多线程，否则退回单流。返回 (文件, 用了什么方式)。"""
    dest_dir = directory or download_dir()
    name = safe_filename(filename or url.rsplit("/", 1)[-1])
    threads = worker_count() if workers is None else max(1, workers)
    total, supports_range = line_file_info(url)
    if supports_range and threads > 1 and total >= PARALLEL_MIN_SIZE:
        return download_parallel(url, dest_dir, name, total, threads), f"{threads} 线程分段 · {ui.human_size(total)}"
    return download(url, name, dest_dir), "单线程流式"
