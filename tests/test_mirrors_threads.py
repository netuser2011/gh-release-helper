# -*- coding: utf-8 -*-
"""线路测速、asyncio 并发分段下载，以及下载方式只剩三项的回归测试。

假服务器只认识 Range 请求，用来回答「文件多大、能不能分段、这一段给你」。
全程不联网：把 dl._client / dl._aclient 换成假 httpx 客户端即可。
"""

import os
import re
import tempfile
import unittest
from contextlib import asynccontextmanager, contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path

import httpx

import downloader as dl
import main as app
import ui

ASSET_URL = "https://github.com/a/b/releases/download/v1/tool.zip"
MIRROR_ID = "ghproxy.net"
MIRROR_URL = "https://ghproxy.net/" + ASSET_URL
MEGABYTE = 1024 * 1024


def payload_bytes(size):
    """一段有规律的假文件内容，方便验证每个字节都落对了位置。"""
    return bytes(range(256)) * (size // 256)


class FakeResponse:
    def __init__(self, status, body, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def iter_bytes(self, chunk_size=1):
        for offset in range(0, len(self._body), chunk_size):
            yield self._body[offset:offset + chunk_size]

    async def aiter_bytes(self, chunk_size=1):
        for chunk in self.iter_bytes(chunk_size):
            yield chunk

    def iter_raw(self, chunk_size=1):
        return self.iter_bytes(chunk_size)

    async def aiter_raw(self, chunk_size=1):
        async for chunk in self.aiter_bytes(chunk_size):
            yield chunk

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeServer:
    """按 Range 头回话的假文件服务器。

    - ``support_range=False``：无视 Range，永远整体 200 返回（很多镜像就这样）
    - ``fail_for``：URL 里含这些片段就抛连接异常，用来模拟线路不通
    - ``status_for``：URL 片段 → 状态码，用来模拟 403 / 404
    """

    def __init__(self, payload=b"", support_range=True, fail_for=(), status_for=None):
        self.payload = payload
        self.support_range = support_range
        self.fail_for = tuple(fail_for)
        self.status_for = dict(status_for or {})
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None, stream=False):
        requested = (headers or {}).get("Range", "")
        self.calls.append({"url": url, "range": requested})
        for needle, code in self.status_for.items():
            if needle in url:
                return FakeResponse(code, b"denied", {"Content-Length": "6"})
        for needle in self.fail_for:
            if needle in url:
                raise httpx.ConnectError(f"模拟：{needle} 连不上")
        match = re.match(r"bytes=(\d+)-(\d+)$", requested)
        if match and self.support_range:
            start, end = int(match.group(1)), int(match.group(2))
            body = self.payload[start:end + 1]
            return FakeResponse(206, body, {
                "Content-Range": f"bytes {start}-{end}/{len(self.payload)}",
                "Content-Length": str(len(body)),
            })
        return FakeResponse(200, self.payload, {"Content-Length": str(len(self.payload))})

    def install(self, test):
        server = self

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            @contextmanager
            def stream(self, method, url, headers=None, **kw):
                yield server.get(url, headers=headers)

        class FakeAsyncClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            @asynccontextmanager
            async def stream(self, method, url, headers=None, **kw):
                yield server.get(url, headers=headers)

        saved_sync, saved_async = dl._client, dl._aclient
        dl._client = FakeClient
        dl._aclient = FakeAsyncClient
        test.addCleanup(setattr, dl, "_client", saved_sync)
        test.addCleanup(setattr, dl, "_aclient", saved_async)
        return self

    def urls(self):
        return [call["url"] for call in self.calls]


class LineUrlTest(unittest.TestCase):
    def test_direct_uses_the_original_address(self):
        self.assertEqual(dl.line_url(ASSET_URL, "direct"), ASSET_URL)

    def test_mirror_prefixes_the_full_url(self):
        self.assertEqual(dl.line_url(ASSET_URL, MIRROR_ID), MIRROR_URL)

    def test_unknown_line_is_refused(self):
        with self.assertRaises(dl.DownloadError):
            dl.line_url(ASSET_URL, "随机一个别人给的站")

    def test_whitelist_is_https_and_has_no_duplicates(self):
        ids = [item["id"] for item in dl.MIRRORS]
        self.assertEqual(len(ids), len(set(ids)), "线路 id 不能重复，否则选线路会选错")
        self.assertEqual(ids[0], "direct", "直连必须排在第一位，是默认与兜底")
        self.assertGreaterEqual(len(ids), 6, "镜像少了就没多少可比的")
        for item in dl.MIRRORS:
            self.assertTrue(item["prefix"] == "" or item["prefix"].startswith("https://"),
                            "镜像必须以 https:// 开头，否则文件在途中可以被人替换")
            self.assertTrue(item["label"], "每条线路都得有个看得懂的名字")

    def test_lines_for_applies_every_prefix_to_the_same_asset(self):
        urls = [item["url"] for item in dl.lines_for(ASSET_URL)]
        self.assertEqual(len(urls), len(dl.MIRRORS))
        self.assertEqual(urls[0], ASSET_URL)
        for item in urls[1:]:
            self.assertTrue(item.endswith(ASSET_URL), "镜像只做前缀拼接，不改资产地址")


class WorkerCountTest(unittest.TestCase):
    def setUp(self):
        self.saved = os.environ.get(dl.WORKERS_ENV)
        self.addCleanup(self.restore)

    def restore(self):
        if self.saved is None:
            os.environ.pop(dl.WORKERS_ENV, None)
        else:
            os.environ[dl.WORKERS_ENV] = self.saved

    def set_env(self, value):
        os.environ[dl.WORKERS_ENV] = value

    def test_default_when_env_absent(self):
        os.environ.pop(dl.WORKERS_ENV, None)
        self.assertEqual(dl.worker_count(), dl.DEFAULT_WORKERS)

    def test_env_can_raise_it(self):
        self.set_env("6")
        self.assertEqual(dl.worker_count(), 6)

    def test_crazy_values_are_clamped(self):
        for raw, expected in (("0", 1), ("-3", 1), ("999", dl.MAX_WORKERS), ("很多", dl.DEFAULT_WORKERS), ("", dl.DEFAULT_WORKERS)):
            self.set_env(raw)
            self.assertEqual(dl.worker_count(), expected, raw)


class SplitsTest(unittest.TestCase):
    def test_ranges_cover_the_file_exactly_once(self):
        for total, workers in ((10, 3), (1, 4), (100, 100), (9999, 7), (2 * MEGABYTE, 8)):
            bounds = dl.splits(total, workers)
            with self.subTest(total=total, workers=workers):
                self.assertEqual(bounds[0][0], 0)
                self.assertEqual(bounds[-1][1], total - 1)
                self.assertEqual(sum(end - start + 1 for start, end in bounds), total)
                for (_, previous_end), (next_start, _) in zip(bounds, bounds[1:]):
                    self.assertEqual(previous_end + 1, next_start, "分段之间不能有缝也不能重叠")

    def test_remainder_goes_to_the_front(self):
        self.assertEqual(dl.splits(10, 3), [(0, 3), (4, 6), (7, 9)])

    def test_more_workers_than_bytes_makes_no_empty_request(self):
        self.assertEqual(dl.splits(2, 8), [(0, 0), (1, 1)])

    def test_unknown_size_is_not_split(self):
        self.assertEqual(dl.splits(0, 4), [])


class ProbeTest(unittest.TestCase):
    def test_a_working_line_reports_latency_and_throughput(self):
        FakeServer(payload_bytes(dl.PROBE_BYTES * 2)).install(self)
        result = dl.probe_line(ASSET_URL)
        self.assertTrue(result["ok"])
        self.assertEqual(result["bytes"], dl.PROBE_BYTES, "测速只该拉那么一小段")
        self.assertGreater(result["speed"], 0)
        self.assertGreaterEqual(result["latency"], 0)
        self.assertEqual(result["error"], "")

    def test_probe_asks_for_a_bounded_slice(self):
        server = FakeServer(payload_bytes(10 * MEGABYTE)).install(self)
        dl.probe_line(ASSET_URL)
        self.assertEqual(server.calls[0]["range"], f"bytes=0-{dl.PROBE_BYTES - 1}")

    def test_connection_failure_is_a_result_not_an_exception(self):
        FakeServer(payload_bytes(1024), fail_for=["ghproxy.net"]).install(self)
        result = dl.probe_line(MIRROR_URL)
        self.assertFalse(result["ok"])
        self.assertIn("连不上", result["error"])

    def test_http_error_status_is_reported(self):
        FakeServer(payload_bytes(1024), status_for={ASSET_URL: 403}).install(self)
        result = dl.probe_line(ASSET_URL)
        self.assertFalse(result["ok"])
        self.assertIn("HTTP 403", result["error"])

    def test_empty_response_counts_as_down(self):
        FakeServer(b"").install(self)
        self.assertIn("没收到任何字节", dl.probe_line(ASSET_URL)["error"])


class ChooseLineTest(unittest.TestCase):
    def test_fixed_line_skips_the_speedtest(self):
        server = FakeServer(payload_bytes(1024)).install(self)
        line, results = dl.choose_line(ASSET_URL, MIRROR_ID)
        self.assertEqual(line["url"], MIRROR_URL)
        self.assertEqual(results, [], "指定了线路就不该再白测一轮")
        self.assertEqual(server.calls, [])

    def canned_probes(self, speeds):
        """把 probe_lines 换成按 URL 查表的假实现，避免测试真的等网络。"""
        saved = dl.probe_lines
        self.addCleanup(setattr, dl, "probe_lines", saved)

        def fake(url, **kwargs):
            results = []
            for item in dl.lines_for(url):
                speed = speeds.get(item["url"], 0.0)
                results.append({**item, "ok": speed > 0, "speed": speed,
                                "latency": 0.1, "bytes": 1024,
                                "error": "" if speed > 0 else "模拟：不通"})
            return results

        dl.probe_lines = fake

    def test_auto_picks_the_fastest_of_all_lines(self):
        speeds = {ASSET_URL: 1.0 * 1024, MIRROR_URL: 9.0 * 1024}
        self.canned_probes(speeds)
        line, results = dl.choose_line(ASSET_URL)
        self.assertEqual(line["id"], MIRROR_ID)
        self.assertEqual(len(results), len(dl.MIRRORS), "每条线路都要出现在明细里，界面才说得清比了什么")

    def test_dead_mirrors_do_not_sink_the_choice(self):
        """公共镜像经常整批失效：只要有一条活的，就不该报错。"""
        self.canned_probes({ASSET_URL: 2.0 * 1024})
        line, results = dl.choose_line(ASSET_URL)
        self.assertEqual(line["id"], "direct")
        self.assertEqual(sum(1 for item in results if not item["ok"]), len(dl.MIRRORS) - 1)

    def test_auto_lists_every_dead_line_when_nothing_works(self):
        self.canned_probes({})
        with self.assertRaises(dl.DownloadError) as ctx:
            dl.choose_line(ASSET_URL)
        message = str(ctx.exception)
        self.assertIn("全都不通", message)
        for item in dl.MIRRORS:
            self.assertIn(item["label"], message, "七条都不通就得逐条写明原因，不能只说一句失败了")
        self.assertIn("浏览器", message)

    def test_unknown_line_id_is_rejected_before_any_request(self):
        with self.assertRaises(dl.DownloadError):
            dl.choose_line(ASSET_URL, "随便一个")


class FileInfoTest(unittest.TestCase):
    def test_size_comes_from_content_range(self):
        FakeServer(payload_bytes(5 * MEGABYTE)).install(self)
        total, supports = dl.line_file_info(ASSET_URL)
        self.assertEqual(total, 5 * MEGABYTE)
        self.assertTrue(supports)

    def test_server_ignoring_range_means_single_stream(self):
        FakeServer(payload_bytes(3 * MEGABYTE), support_range=False).install(self)
        total, supports = dl.line_file_info(ASSET_URL)
        self.assertFalse(supports)
        self.assertEqual(total, 3 * MEGABYTE)

    def test_unreachable_address_is_explained(self):
        FakeServer(b"", fail_for=["github.com"]).install(self)
        with self.assertRaises(dl.DownloadError) as ctx:
            dl.line_file_info(ASSET_URL)
        self.assertIn("连不上下载地址", str(ctx.exception))


class ParallelDownloadTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        saved = dl.ui.is_tty
        dl.ui.is_tty = lambda: False
        self.addCleanup(setattr, dl.ui, "is_tty", saved)

    def test_every_segment_lands_at_its_own_offset(self):
        data = payload_bytes(3 * MEGABYTE)
        server = FakeServer(data).install(self)
        saved = dl.download_parallel(ASSET_URL, self.dir, "tool.zip", len(data), 4)
        self.assertEqual(saved.read_bytes(), data, "分段下载最容易错在偏移量，逐字节比对才算过")
        self.assertEqual(saved.name, "tool.zip")
        ranges = [call["range"] for call in server.calls if call["range"] != "bytes=0-0"]
        self.assertEqual(len(ranges), 4)
        self.assertEqual(list(self.dir.iterdir()), [saved], "不该留下 .part")

    def test_broken_segment_removes_the_temp_file(self):
        data = payload_bytes(3 * MEGABYTE)
        FakeServer(data, status_for={MIRROR_URL: 403}).install(self)
        with self.assertRaises(dl.DownloadError) as ctx:
            dl.download_parallel(MIRROR_URL, self.dir, "tool.zip", len(data), 3)
        self.assertIn("不支持分段", str(ctx.exception))
        self.assertEqual(list(self.dir.iterdir()), [], "半截文件必须清干净")

    def test_wrong_length_is_not_renamed_into_a_real_file(self):
        """服务器谎报 Content-Range 总长时，字节数对不上就不能算下载完成。"""
        data = payload_bytes(3 * MEGABYTE)
        server = FakeServer(data).install(self)
        original = server.get

        def lying_get(url, params=None, headers=None, timeout=None, stream=False):
            resp = original(url, params, headers, timeout, stream)
            if resp.status_code == 206:
                resp._body = resp._body[:-1]  # 每段都少给一个字节
                resp.headers["Content-Length"] = str(len(resp._body))
            return resp

        server.get = lying_get
        server.install(self)
        with self.assertRaises(dl.DownloadError) as ctx:
            dl.download_parallel(ASSET_URL, self.dir, "tool.zip", len(data), 2)
        self.assertIn("不完整", str(ctx.exception))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_unknown_size_is_refused_instead_of_a_thread_crash(self):
        """线程数为 0 会让 ThreadPoolExecutor 直接 ValueError，这里必须提前拦住。"""
        FakeServer(b"").install(self)
        with self.assertRaises(dl.DownloadError) as ctx:
            dl.download_parallel(ASSET_URL, self.dir, "tool.zip", 0, 4)
        self.assertIn("大小未知", str(ctx.exception))
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_existing_name_still_gets_a_suffix(self):
        data = payload_bytes(3 * MEGABYTE)
        FakeServer(data).install(self)
        (self.dir / "tool.zip").write_bytes(b"old")
        saved = dl.download_parallel(ASSET_URL, self.dir, "tool.zip", len(data), 2)
        self.assertEqual(saved.name, "tool(1).zip")
        self.assertEqual((self.dir / "tool.zip").read_bytes(), b"old", "不能覆盖用户已有文件")


class DiscardPartTest(unittest.TestCase):
    """清理临时文件不能反过来制造新异常，盖住正在上报的下载错误。"""

    def test_locked_part_and_meta_do_not_raise(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        part = root / "tool.zip.part"
        part.write_bytes(b"half")
        meta = dl._meta_path(part)
        meta.write_text("{}", encoding="utf-8")
        # Windows 上 open 着的 .part 无法 unlink（WinError 32），这正是杀软占用的场景
        with part.open("rb"), meta.open("rb"):
            dl._discard_part(part)


class FetchTest(unittest.TestCase):
    """fetch() 是终端下载唯一的入口：决定用不用多线程，然后干活。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        saved = dl.ui.is_tty
        dl.ui.is_tty = lambda: False
        self.addCleanup(setattr, dl.ui, "is_tty", saved)

    def test_big_ranged_file_goes_parallel(self):
        data = payload_bytes(dl.PARALLEL_MIN_SIZE + MEGABYTE)
        FakeServer(data).install(self)
        saved, how = dl.fetch(ASSET_URL, "tool.zip", self.dir)
        self.assertIn("并发分段", how)
        self.assertEqual(saved.read_bytes(), data)

    def test_small_file_stays_single_stream(self):
        FakeServer(payload_bytes(256 * 1024)).install(self)
        saved, how = dl.fetch(ASSET_URL, "tool.zip", self.dir)
        self.assertEqual(how, "单流下载")
        self.assertEqual(saved.read_bytes(), payload_bytes(256 * 1024))

    def test_no_range_support_falls_back(self):
        data = payload_bytes(3 * MEGABYTE)
        FakeServer(data, support_range=False).install(self)
        saved, how = dl.fetch(ASSET_URL, "tool.zip", self.dir)
        self.assertEqual(how, "单流下载")
        self.assertEqual(saved.read_bytes(), data)

    def test_single_worker_never_opens_a_thread_pool(self):
        data = payload_bytes(3 * MEGABYTE)
        server = FakeServer(data).install(self)
        _, how = dl.fetch(ASSET_URL, "tool.zip", self.dir, workers=1)
        self.assertEqual(how, "单流下载")
        self.assertFalse([c for c in server.calls if c["range"] not in ("bytes=0-0", "")],
                         "workers=1 时不该再分段请求")


class DownloadChoicesTest(unittest.TestCase):
    """下载方式的回归：只剩三项，且任何一项都不会「浏览器 + 本地」各下一遍。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.local = []
        self.browser = []
        self.offers = []
        self.routes_asked = 0

        for target, name in ((app.dl, "open_in_browser"), (app.dl, "fetch"), (app.dl, "choose_line"),
                             (app, "choose_destination"), (app, "choose_route"), (ui, "choose")):
            self.addCleanup(setattr, target, name, getattr(target, name))

        def fake_fetch(url, name, directory):
            path = Path(directory) / name
            path.write_bytes(b"x")
            self.local.append(name)
            return path, "4 线程分段 · 3.0 MB"

        app.dl.fetch = fake_fetch
        app.dl.open_in_browser = lambda url: (self.browser.append(url), True)[1]
        app.dl.choose_line = lambda url, mirror: ({"id": mirror, "label": "直连 GitHub", "url": url}, [])
        app.choose_destination = lambda: self.dir

        def fake_route():
            self.routes_asked += 1
            return "direct"

        app.choose_route = fake_route

    def ask(self, answer, route="direct"):
        def fake_route():
            self.routes_asked += 1
            return route

        def fake_choose(prompt, count, allow_zero=False):
            self.offers.append(count)
            return answer

        app.choose_route = fake_route
        ui.choose = fake_choose
        buf = StringIO()
        with redirect_stdout(buf):
            app.do_download("a/b", {"name": "tool.zip", "browser_download_url": ASSET_URL, "size": 3 * MEGABYTE})
        return buf.getvalue()

    def test_the_menu_offers_exactly_three_ways(self):
        self.ask(3)
        self.assertEqual(self.offers, [3], "下载方式只剩三项")

    def test_terminal_download_touches_the_local_disk_only(self):
        out = self.ask(1)
        self.assertEqual(self.local, ["tool.zip"])
        self.assertEqual(self.browser, [], "选了终端下载就不该再唤起浏览器——那正是「下两遍」的来源")
        self.assertIn("下载完成", out)

    def test_browser_download_never_writes_locally(self):
        self.ask(2)
        self.assertEqual(self.browser, [ASSET_URL])
        self.assertEqual(self.local, [])

    def test_link_mode_opens_nothing(self):
        out = self.ask(3)
        self.assertEqual((self.browser, self.local), ([], []))
        self.assertIn(ASSET_URL, out)

    def test_terminal_download_asks_which_line(self):
        self.ask(1)
        self.assertEqual(self.routes_asked, 1)

    def test_back_out_changes_nothing(self):
        out = self.ask(0)
        self.assertEqual((self.browser, self.local), ([], []))
        self.assertEqual(self.routes_asked, 0, "在第一步就返回，不该继续追问线路")

    def test_mirror_choice_is_passed_through(self):
        """选镜像时，实际请求的地址必须带上 ghproxy.net 前缀。"""
        used = {}

        def fake_fetch(url, name, directory):
            used["url"] = url
            path = directory / name
            path.write_bytes(b"x")
            return path, "4 线程分段 · 3.0 MB"

        app.dl.fetch = fake_fetch

        def line(url, mirror):
            return {"id": mirror, "label": "镜像 ghproxy.net", "url": dl.line_url(url, mirror)}, []

        app.dl.choose_line = line
        self.ask(1, route=MIRROR_ID)
        self.assertEqual(used["url"], MIRROR_URL)

    def test_dead_lines_are_reported_without_a_crash(self):
        def dead(url, mirror):
            raise app.dl.DownloadError("7 条线路全都不通：直连 GitHub：模拟超时")

        app.dl.choose_line = dead
        out = self.ask(1)
        self.assertIn("全都不通", out)
        self.assertEqual(self.local, [])


class RouteMenuTest(unittest.TestCase):
    """线路菜单跟着白名单走：加一条镜像不用改界面代码。"""

    def test_auto_is_first_and_every_line_follows(self):
        choices = app.route_choices()
        self.assertEqual(choices[0][1], dl.AUTO_ROUTE)
        self.assertEqual([item[1] for item in choices[1:]], [item["id"] for item in dl.MIRRORS])

    def test_choosing_a_number_returns_that_line(self):
        saved_choose, saved_tty = ui.choose, ui.is_tty
        self.addCleanup(setattr, ui, "choose", saved_choose)
        self.addCleanup(setattr, ui, "is_tty", saved_tty)
        ui.is_tty = lambda: True
        asked = {}

        def fake_choose(prompt, count, allow_zero=False):
            asked["count"] = count
            return len(dl.MIRRORS) + 1      # 选最后一条线路

        ui.choose = fake_choose
        buf = StringIO()
        with redirect_stdout(buf):
            picked = app.choose_route()
        self.assertEqual(picked, dl.MIRRORS[-1]["id"])
        self.assertEqual(asked["count"], len(dl.MIRRORS) + 1, "菜单条数 = 自动测速 + 全部线路")
        self.assertIn("自动测速", buf.getvalue())

    def test_back_out_returns_none(self):
        saved_choose = ui.choose
        self.addCleanup(setattr, ui, "choose", saved_choose)
        ui.choose = lambda prompt, count, allow_zero=False: 0
        buf = StringIO()
        with redirect_stdout(buf):
            self.assertIsNone(app.choose_route())


class ProbeConcurrencyTest(unittest.TestCase):
    """七条线路必须一起测：串行等待会让最坏情况变成 7 × 超时。"""

    def canned(self, behaviour):
        saved = dl._probe
        self.addCleanup(setattr, dl, "_probe", saved)
        seen = []

        async def fake(client, line, *a, **kw):
            seen.append(line["url"])
            return behaviour(line["url"])

        dl._probe = fake
        return seen

    def test_every_line_is_probed_once(self):
        seen = self.canned(lambda url: {"ok": True, "speed": 1.0, "latency": 0.1,
                                        "bytes": 1024, "error": ""})
        results = dl.probe_lines(ASSET_URL)
        self.assertEqual(sorted(seen), sorted(item["url"] for item in dl.lines_for(ASSET_URL)))
        self.assertEqual(len(results), len(dl.MIRRORS))

    def test_total_wait_is_one_round_not_a_queue(self):
        import asyncio
        import time

        async def slow(client, line, *a, **kw):
            await asyncio.sleep(0.25)
            return {"ok": True, "speed": 1.0, "latency": 0.25, "bytes": 1024, "error": ""}

        saved = dl._probe
        self.addCleanup(setattr, dl, "_probe", saved)
        dl._probe = slow
        started = time.time()
        dl.probe_lines(ASSET_URL)
        elapsed = time.time() - started
        serial = 0.25 * len(dl.MIRRORS)
        self.assertLess(elapsed, serial / 2,
                        f"并发测速不该接近串行的 {serial:.2f} 秒，实测 {elapsed:.2f} 秒")

    def test_a_line_that_never_answers_is_cut_off(self):
        import asyncio

        async def hang(client, line, *a, **kw):
            await asyncio.sleep(3)
            return {"ok": True, "speed": 1.0, "latency": 0.0, "bytes": 1024, "error": ""}

        saved = dl._probe
        self.addCleanup(setattr, dl, "_probe", saved)
        dl._probe = hang
        results = dl.probe_lines(ASSET_URL, wall_timeout=0.2)
        self.assertEqual(len(results), len(dl.MIRRORS), "超时的线路也要在明细里占一行")
        for item in results:
            self.assertFalse(item["ok"])
            self.assertIn("未返回", item["error"])


class NoProxyCompatTest(unittest.TestCase):
    """代理工具写进 NO_PROXY 的 [::1] 会让 httpx 抛 InvalidURL，测速与下载会全线崩。"""

    HOSTILE = "localhost,.localhost,127.0.0.1,127.0.0.0/8,[::1],::1"

    def setUp(self):
        self.saved = {var: os.environ.get(var) for var in dl.NO_PROXY_VARS}
        self.addCleanup(self.restore)

    def restore(self):
        for var, value in self.saved.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value

    def set_hostile(self):
        for var in dl.NO_PROXY_VARS:
            os.environ[var] = self.HOSTILE

    def test_ipv6_literals_are_dropped(self):
        self.assertEqual(dl._clean_no_proxy(self.HOSTILE),
                         "localhost,.localhost,127.0.0.1,127.0.0.0/8")

    def test_both_clients_construct_under_hostile_no_proxy(self):
        self.set_hostile()
        with dl._client() as sync_client:
            self.assertIsNotNone(sync_client)

        import asyncio

        async def make_async():
            client = dl._aclient()
            await client.aclose()
            return True

        self.assertTrue(asyncio.run(make_async()))

    def test_environment_is_restored_after_construction(self):
        self.set_hostile()
        with dl._client():
            pass
        for var in dl.NO_PROXY_VARS:
            self.assertEqual(os.environ[var], self.HOSTILE, "清洗只该在构造期间生效")


class SpeedtestTableTest(unittest.TestCase):
    """测速表：哪条被选中、不通的那条为什么不通，都得一眼看出来。"""

    def rows(self, chosen):
        results = [
            {"id": "direct", "label": "直连 GitHub", "url": ASSET_URL, "ok": True,
             "speed": 1024.0, "latency": 0.31, "bytes": 1024, "error": ""},
            {"id": "ghproxy", "label": "镜像 ghproxy.net", "url": MIRROR_URL, "ok": True,
             "speed": 9216.0, "latency": 2.0, "bytes": 1024, "error": ""},
            {"id": "broken", "label": "线路已下线", "url": "x", "ok": False,
             "speed": 0.0, "latency": 0.0, "bytes": 0, "error": "模拟：连接被重置"},
        ]
        buf = StringIO()
        with redirect_stdout(buf):
            app.report_speedtest(results, dict(chosen))   # 故意传副本：判定不能依赖是不是同一个对象
        return buf.getvalue().splitlines()

    def test_marker_lands_on_the_chosen_row(self):
        lines = self.rows({"id": "ghproxy"})
        marked = [line for line in lines if "已选中" in line]
        self.assertEqual(len(marked), 1)
        self.assertIn("ghproxy.net", marked[0])
        self.assertNotIn("直连", marked[0])

    def test_throughput_and_latency_are_printed(self):
        text = "\n".join(self.rows({"id": "direct"}))
        self.assertIn("310 ms", text)
        self.assertIn("9 KB/s", text)

    def test_dead_line_shows_its_reason(self):
        text = "\n".join(self.rows({"id": "direct"}))
        self.assertIn("不通", text)
        self.assertIn("连接被重置", text)

    def test_lines_are_sorted_fastest_first_and_dead_last(self):
        lines = self.rows({"id": "ghproxy"})
        text = "\n".join(lines)
        position = lambda needle: next(index for index, line in enumerate(lines) if needle in line)
        self.assertLess(position("ghproxy.net"), position("直连 GitHub"), "快的排上面，一眼就知道该选谁")
        self.assertLess(position("直连 GitHub"), position("线路已下线"))
        self.assertIn("不通", text)


if __name__ == "__main__":
    unittest.main()
