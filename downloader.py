#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载能力：httpx + asyncio 并发分段下载、线路测速、浏览器与链接备选。"""
from __future__ import annotations
import asyncio
import json
import os
import re
import webbrowser
from contextlib import contextmanager
from pathlib import Path
import httpx
import time
import ui
CHUNK = 256 * 1024
DOWNLOAD_DIR_ENV = "GHR_DOWNLOAD_DIR"
CONFIG_FILE = Path(__file__).resolve().with_name("config.json")
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Windows 保留设备名：不带扩展名的 CON / NUL / COM1 等直接 open 会失败
_WINDOWS_RESERVED = frozenset(
    ("CON", "PRN", "AUX", "NUL",
     *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10)))
)
# 镜像写死白名单：把下载地址交给任意第三方，等于让人有机会替换文件内容。
MIRRORS = tuple({"id": i, "label": i if i != "direct" else "直连 GitHub",
                 "prefix": "" if i == "direct" else f"https://{i}/"}
                for i in ("direct", "ghproxy.net", "gh-proxy.com", "ghfast.top",
                          "gh-proxy.org", "gh-proxy.eu.org", "ghp.keleyaa.com"))
AUTO_ROUTE = "auto"
PROBE_BYTES, PROBE_TIMEOUT, PROBE_GRACE = 128 * 1024, 6, 2
RANGE_TIMEOUT, PARALLEL_MIN_SIZE = (15, 60), 512 * 1024
DEFAULT_WORKERS, MAX_WORKERS, WORKERS_ENV = 8, 16, "GHR_THREADS"
class DownloadError(Exception):
    """下载过程中的可预期失败。"""
class ResumableDownloadError(DownloadError):
    """中断或取消：.part 保留，下次从断点继续。"""

PROGRESS_VERSION = 1
_meta_path = lambda part: part.with_name(part.name + ".meta")
def _read_progress(part: Path) -> dict | None:
    try:
        raw = json.loads(_meta_path(part).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (OSError, ValueError):
        return None
def _write_progress(part: Path, info: dict) -> None:
    meta = _meta_path(part)
    tmp = meta.with_suffix(".meta.tmp")
    try:
        tmp.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        tmp.replace(meta)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
def _discard_part(part: Path) -> None:
    part.unlink(missing_ok=True)
    _meta_path(part).unlink(missing_ok=True)
def _can_resume(part: Path, meta: dict | None, url: str, total: int,
                etag: str, modified: str, mode: str) -> bool:
    if not meta or meta.get("v") != PROGRESS_VERSION:
        return False
    if (meta.get("url"), meta.get("total"), meta.get("mode")) != (url, total, mode):
        return False
    if ((meta.get("etag", "") and etag and meta["etag"] != etag) or
            (meta.get("last_modified", "") and modified and meta["last_modified"] != modified)):
        return False
    return part.is_file()

def load_config() -> dict:
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}
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
    config = load_config()
    config["download_dir"] = str(Path(path).expanduser().resolve())
    save_config(config)
    return Path(config["download_dir"])
def clear_default_download_dir() -> None:
    config = load_config()
    if config.pop("download_dir", None) is not None:
        save_config(config)
def system_download_dir() -> Path:
    home = Path.home()
    return next((home / d for d in ("Downloads", "下载") if (home / d).is_dir()), home / "Downloads")
def resolve_download_dir() -> Path:
    """环境变量 > config.json > 系统下载目录；只算路径，不碰文件系统。"""
    env = os.environ.get(DOWNLOAD_DIR_ENV, "").strip()
    if env:
        return Path(env).expanduser()
    saved = str(load_config().get("download_dir", "")).strip()
    return Path(saved).expanduser() if saved else system_download_dir()
def download_dir() -> Path:
    target = resolve_download_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DownloadError(f"无法创建下载目录 {target}：{exc}") from exc
    return target
def safe_filename(name: str, fallback: str = "release-asset") -> str:
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _ILLEGAL.sub("", base).strip().strip(".")
    if cleaned and cleaned.upper() in _WINDOWS_RESERVED:
        cleaned += "_"  # CON / NUL / COM1 这类保留名加下划线，避免 Windows 打开失败
    return (cleaned or fallback)[:150]
def unique_path(directory: Path, filename: str) -> Path:
    """同名文件自动加 (1)(2)，绝不覆盖用户已有文件。"""
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
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False

NO_PROXY_VARS = ("NO_PROXY", "no_proxy")


def _no_proxy_entry_ok(entry: str) -> bool:
    """httpx 把 NO_PROXY 的每一项当 URL 解析，IPv6 字面量（[::1]、::1）会在
    normalize_port 上抛 InvalidURL，直接把测速和下载打死。代理工具（Watt Toolkit
    等）习惯把这些写进 NO_PROXY，所以这一步不是可选的。"""
    return not any(ch in entry for ch in "[]:")


def _clean_no_proxy(raw: str) -> str:
    kept = [e.strip() for e in raw.split(",") if e.strip() and _no_proxy_entry_ok(e.strip())]
    return ",".join(kept)


@contextmanager
def _httpx_friendly_env():
    """构造客户端的那一小段时间里，把 NO_PROXY 洗成 httpx 认的写法，出来就还原。
    只影响 httpx：requests/urllib3 自己会做 fnmatch，遇到这些条目不会报错。"""
    saved: list[tuple[str, str]] = []
    for var in NO_PROXY_VARS:
        raw = os.environ.get(var, "")
        if not raw:
            continue
        cleaned = _clean_no_proxy(raw)
        if cleaned != raw:
            saved.append((var, raw))
            os.environ[var] = cleaned
    try:
        yield
    finally:
        for var, raw in saved:
            os.environ[var] = raw


def _client(timeout=RANGE_TIMEOUT) -> httpx.Client:
    # truststore 已在启动时注入系统证书，无需再传 verify 路径
    with _httpx_friendly_env():
        return httpx.Client(follow_redirects=True, timeout=timeout)
def _aclient(timeout=RANGE_TIMEOUT) -> httpx.AsyncClient:
    with _httpx_friendly_env():
        return httpx.AsyncClient(follow_redirects=True, timeout=timeout)

# TUI 注入的进度回调：签名 (done, total, rate) -> None。CLI 下为 None，
# _bar 用 \r 重绘；Textual 全屏时由 tui.py 设置，把进度送到界面组件
# （直接 print 会被 TUI 的屏幕缓冲区吞掉，所以必须走回调）。
progress_hook = None

@contextmanager
def _bar(total: int, desc: str):
    """TTY 下 \r 重绘进度；TUI 注入 progress_hook 时改走回调。"""
    if progress_hook is None and not ui.is_tty():
        yield None
        return
    done = 0
    started = time.monotonic()

    def tick(n: int) -> None:
        nonlocal done
        done += n
        rate = done / max(0.001, time.monotonic() - started)
        if progress_hook is not None:
            progress_hook(done, total, rate)
        elif ui.is_tty():
            print("\r  " + desc + " " + ui.progress_render(done, total, rate), end="", flush=True)

    try:
        yield tick
    finally:
        if progress_hook is None and ui.is_tty():
            print(flush=True)
def _brief_error(exc: BaseException) -> str:
    return re.sub(r"\s+", " ", str(exc).strip() or exc.__class__.__name__)[:120]
def _as_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

def worker_count() -> int:
    try:
        return max(1, min(int(os.environ.get(WORKERS_ENV, "").strip()), MAX_WORKERS))
    except ValueError:
        return DEFAULT_WORKERS
def line_url(url: str, mirror_id: str) -> str:
    for item in MIRRORS:
        if item["id"] == mirror_id:
            return f"{item['prefix']}{url}" if item["prefix"] else url
    raise DownloadError(f"未知线路：{mirror_id}")
def lines_for(url: str) -> list[dict]:
    return [{"id": i["id"], "label": i["label"], "url": line_url(url, i["id"])} for i in MIRRORS]

_bad = lambda reason: {"ok": False, "speed": 0.0, "latency": 0.0, "bytes": 0, "error": reason}
async def _probe(client: httpx.AsyncClient, line: dict,
                 max_bytes: int = PROBE_BYTES, timeout: int = PROBE_TIMEOUT) -> dict:
    """测一条线路：拉前一小段，返回首字节延迟与吞吐；不通返回原因。"""
    loop = asyncio.get_running_loop()
    started, first, got = loop.time(), 0.0, 0
    try:
        async with client.stream("GET", line["url"],
                                 headers={"Range": f"bytes=0-{max_bytes - 1}"}) as resp:
            if resp.status_code not in (200, 206):
                return _bad(f"HTTP {resp.status_code}")
            async for chunk in resp.aiter_raw(min(CHUNK, 32 * 1024)):
                if chunk:
                    if not first:
                        first = loop.time() - started
                    got += len(chunk)
                    if got >= max_bytes or loop.time() - started >= timeout:
                        break
    except (httpx.HTTPError, OSError) as exc:
        return _bad(_brief_error(exc))
    if not got:
        return _bad("没收到任何字节")
    elapsed = max(loop.time() - started, 1e-6)
    # 首字节延迟（TLS 握手 / 服务器响应）不该算进吞吐：高延迟链路上
    # 5 秒等首字节 + 0.3 秒传完，按总耗时会算成 25KB/s，把好线路误判成慢线路。
    # 传输样本太短（一个 chunk 就送完）时退回总耗时，避免算出虚高速度。
    transfer = elapsed - first
    speed = got / (transfer if transfer >= 0.2 else elapsed)
    return {"ok": True, "speed": speed, "latency": first or elapsed,
            "bytes": got, "error": ""}
def probe_line(url: str, max_bytes: int = PROBE_BYTES, timeout: int = PROBE_TIMEOUT) -> dict:
    async def run():
        async with _aclient(timeout=timeout) as client:
            return await _probe(client, {"url": url}, max_bytes, timeout)
    return asyncio.run(run())
def probe_lines(url: str, wall_timeout: int = 0) -> list[dict]:
    """并发测全部线路；超时的记原因，其余照常参与比较。"""
    lines = lines_for(url)
    budget = wall_timeout or (PROBE_TIMEOUT + PROBE_GRACE)
    async def run():
        async with _aclient() as client:
            tasks = [asyncio.create_task(_probe(client, item)) for item in lines]
            done, pending = await asyncio.wait(tasks, timeout=budget)
            measured: dict[int, dict] = {}
            for task in done:
                exc = task.exception()
                # done 里带异常的任务不能裸 result()：会把测速的意外
                # 抛穿整个下载流程，转成该线路的"不通"明细
                measured[tasks.index(task)] = _bad(f"测速异常：{exc}") if exc is not None else task.result()
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.wait(pending)
            return measured
    measured = asyncio.run(run())
    late = _bad(f"测速超过 {budget} 秒未返回")
    return [{**item, **measured.get(i, late)} for i, item in enumerate(lines)]
def best_line(results: list[dict]) -> dict | None:
    passed = [item for item in results if item.get("ok")]
    return max(passed, key=lambda item: item["speed"]) if passed else None
def choose_line(url: str, mirror: str = AUTO_ROUTE) -> tuple[dict, list[dict]]:
    if mirror and mirror != AUTO_ROUTE:
        for item in lines_for(url):
            if item["id"] == mirror:
                return item, []
        raise DownloadError(f"未知线路：{mirror}（可选 {', '.join(m['id'] for m in MIRRORS)} 或 auto）")
    results = probe_lines(url)
    chosen = best_line(results)
    if chosen is None:
        detail = "\n".join(f"       · {i['label']}：{(i['error'] or '不通')[:70]}" for i in results)
        raise DownloadError(
            f"{len(results)} 条线路全都不通：{detail}\n"
            "     可以先改用浏览器方式下载，或检查本机代理 / hosts；"
            "代理工具做 HTTPS 中间人时也长这样。")
    return chosen, results
def line_file_info(url: str) -> tuple[int, bool]:
    total, supports, _, _ = line_file_info_full(url)
    return total, supports
def line_file_info_full(url: str) -> tuple[int, bool, str, str]:
    """问服务器：文件多大、支不支持 Range、ETag、Last-Modified。"""
    try:
        with _client() as client, client.stream("GET", url,
                                                headers={"Range": "bytes=0-0"}) as resp:
            supports = resp.status_code == 206
            match = re.search(r"/(\d+)\s*$", resp.headers.get("Content-Range", ""))
            total = _as_int(match.group(1)) if match else _as_int(resp.headers.get("Content-Length"))
            return total, supports, (resp.headers.get("ETag") or "").strip(), \
                (resp.headers.get("Last-Modified") or "").strip()
    except httpx.HTTPError as exc:
        raise DownloadError(f"连不上下载地址：{_brief_error(exc)}") from exc
def splits(total: int, workers: int) -> list[tuple[int, int]]:
    if total <= 0:
        return []
    workers = max(1, min(workers, total))
    size, extra = divmod(total, workers)
    bounds, start = [], 0
    for index in range(workers):
        length = size + (1 if index < extra else 0)
        bounds.append((start, start + length - 1))
        start += length
    return bounds

def _check_file(part: Path, dest: Path, final: int, total: int) -> Path:
    if not final or (total and final != total):
        _discard_part(part)
        raise DownloadError("下载到的文件是空的，链接可能已失效。" if not final
                            else f"文件不完整（{final}/{total} 字节），已放弃。")
    _meta_path(part).unlink(missing_ok=True)
    return part.replace(dest)
def download(url: str, filename: str = "", directory: Path | None = None,
             total_hint: int = 0, etag: str = "", modified: str = "") -> Path:
    """流式下载，支持断点续传；中断保留进度，永久性失败清理干净。"""
    dest_dir = directory or download_dir()
    dest = unique_path(dest_dir, safe_filename(filename or url.rsplit("/", 1)[-1]))
    part = dest.with_name(dest.name + ".part")
    meta = _read_progress(part) or {}
    offset = 0
    if meta and meta.get("mode") == "stream" and meta.get("url") == url and part.is_file():
        if not ((meta.get("etag", "") and etag and meta["etag"] != etag) or
                (meta.get("last_modified", "") and modified and meta["last_modified"] != modified)):
            offset = part.stat().st_size
    if not offset:
        _discard_part(part)
        meta = {"v": PROGRESS_VERSION, "url": url, "mode": "stream", "total": total_hint,
                "etag": etag, "last_modified": modified}
    appended = bool(offset)
    written = 0
    total = 0
    try:
        headers = {"Range": f"bytes={offset}-"} if appended else {}
        with _client(timeout=30) as client, client.stream("GET", url, headers=headers) as resp:
            if not appended and resp.status_code != 200:
                raise DownloadError(f"下载失败（HTTP {resp.status_code}），请确认链接是否还有效：{url}")
            if appended:
                if resp.status_code == 206:
                    match = re.search(r"/(\d+)\s*$", resp.headers.get("Content-Range", ""))
                    total = _as_int(match.group(1)) if match else offset + _as_int(resp.headers.get("Content-Length"))
                elif resp.status_code == 200:
                    appended, offset = False, 0
                else:
                    raise DownloadError(f"续传失败（HTTP {resp.status_code}）：{url}")
            total = total or _as_int(resp.headers.get("Content-Length"))
            if not total and "text/html" in resp.headers.get("Content-Type", ""):
                raise DownloadError(f"服务器返回的是网页而不是文件，链接可能已失效：{url}")
            meta["total"] = total
            _write_progress(part, meta)
            with _bar(total, "下载") as tick, part.open("ab" if appended else "wb") as fh:
                for chunk in resp.iter_raw(CHUNK):
                    if chunk:
                        fh.write(chunk)
                        written += len(chunk)
                        if tick:
                            tick(len(chunk))
    except (KeyboardInterrupt, httpx.HTTPError) as exc:
        if isinstance(exc, KeyboardInterrupt):
            print()
        _write_progress(part, meta)
        raise ResumableDownloadError(
            f"下载中断，已保留 {ui.human_size(offset + written)} 进度，下次重跑会从断点继续。") from None
    except DownloadError:
        _discard_part(part)
        raise
    except OSError as exc:
        _discard_part(part)
        raise DownloadError(f"写入文件失败（{dest_dir}）：{exc}") from exc
    return _check_file(part, dest, offset + written, total)
async def _fetch_part(client: httpx.AsyncClient, url: str, start: int, end: int,
                      part: Path, tick) -> int:
    """asyncio 并发下载一段，直接写进 .part 的对应偏移；协程内无共享写锁。"""
    expected = end - start + 1
    written = 0
    try:
        async with client.stream("GET", url, headers={"Range": f"bytes={start}-{end}"}) as resp:
            if resp.status_code != 206:
                raise DownloadError(f"线路中途不支持分段（HTTP {resp.status_code}）")
            with part.open("rb+") as fh:
                fh.seek(start)
                async for chunk in resp.aiter_raw(CHUNK):
                    if chunk:
                        fh.write(chunk)
                        written += len(chunk)
                        if tick:
                            tick(len(chunk))
    except asyncio.CancelledError:
        # 取消是控制流，不是业务失败：必须原样抛回给 gather/run，
        # 否则会盖住真正的首个异常，并在事件循环关闭时留下 unhandled task。
        raise
    except httpx.HTTPError as exc:
        raise ResumableDownloadError(f"分段下载中断：{_brief_error(exc)}") from exc
    except DownloadError:
        raise
    except OSError as exc:
        raise DownloadError(f"写入文件失败（{part}）：{exc}") from exc
    if written != expected:
        raise DownloadError(f"分段不完整（{written}/{expected} 字节）")
    return written
def download_parallel(url: str, directory: Path, filename: str, total: int, workers: int,
                      etag: str = "", modified: str = "") -> Path:
    """asyncio.gather 并发分段；.meta 记录每段完成状态，中断只补未完成的段。"""
    dest = unique_path(directory, safe_filename(filename))
    part = dest.with_name(dest.name + ".part")
    bounds = splits(total, workers)
    if not bounds:
        raise DownloadError("文件大小未知，无法分段下载。")
    meta = _read_progress(part) or {}
    resuming = _can_resume(part, meta, url, total, etag, modified, "parallel") and \
        meta.get("bounds") == [list(b) for b in bounds] and \
        isinstance(meta.get("done"), list) and len(meta.get("done", [])) == len(bounds) and \
        part.stat().st_size == total
    if resuming:
        done = [bool(x) for x in meta["done"]]
    else:
        done = [False] * len(bounds)
        _discard_part(part)
        with part.open("wb") as fh:
            fh.truncate(total)
        meta = {"v": PROGRESS_VERSION, "url": url, "total": total, "mode": "parallel",
                "etag": etag, "last_modified": modified,
                "bounds": [list(b) for b in bounds], "done": done}
        _write_progress(part, meta)
    pending = [i for i, ok in enumerate(done) if not ok]
    done_bytes = sum(bounds[i][1] - bounds[i][0] + 1 for i, ok in enumerate(done) if ok)
    async def run():
        # 并发分段用更短的读超时：镜像拒绝并发 Range 时尽快失败，好回退单流，
        # 不能让用户对着卡死的进度条等一分钟。
        async with _aclient(timeout=(10, 20)) as client:
            with _bar(total, "下载") as tick:
                async def fetch_one(i: int):
                    await _fetch_part(client, url, bounds[i][0], bounds[i][1], part, tick)
                    done[i] = True
                    meta["done"] = done[:]
                    _write_progress(part, meta)
                await asyncio.gather(*[fetch_one(i) for i in pending])
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, ResumableDownloadError) as exc:
        if isinstance(exc, KeyboardInterrupt):
            print()
        _write_progress(part, meta)
        raise ResumableDownloadError(
            f"下载中断，已保留 {ui.human_size(done_bytes)} 进度，下次重跑只补未完成的段。") from None
    except asyncio.CancelledError as exc:
        # 任务被取消（并发被服务器/代理打断）：保留进度但按可失败处理，交给 fetch 回退单流
        _write_progress(part, meta)
        raise DownloadError(f"并发分段被取消：{_brief_error(exc)}") from exc
    except DownloadError:
        _discard_part(part)
        raise
    except Exception as exc:  # noqa: BLE001  协程里的意外不该以 traceback 收场
        _discard_part(part)
        raise DownloadError(f"下载失败：{_brief_error(exc)}") from exc
    return _check_file(part, dest, total, total)
def fetch(url: str, filename: str = "", directory: Path | None = None,
          workers: int | None = None) -> tuple[Path, str]:
    """终端下载唯一入口：优先并发分段；并发被限制时自动回退单流，保证能下完。"""
    dest_dir = directory or download_dir()
    name = safe_filename(filename or url.rsplit("/", 1)[-1])
    count = worker_count() if workers is None else max(1, workers)
    total, supports_range, etag, modified = line_file_info_full(url)
    if supports_range and count > 1 and total >= PARALLEL_MIN_SIZE:
        try:
            saved = download_parallel(url, dest_dir, name, total, count, etag, modified)
            return saved, f"{count} 并发分段 · {ui.human_size(total)}"
        except ResumableDownloadError:
            raise  # 用户主动中断：尊重，不要偷偷换成单流重下
        except DownloadError as exc:
            # 镜像假支持 Range / 代理限制并发连接：退回单流，慢一点但一定下得完
            print(f"  并发分段失败（{exc}），改用单流重试 ...")
    return download(url, name, dest_dir, total, etag, modified), "单流下载"
