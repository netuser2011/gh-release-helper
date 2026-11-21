# 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循
[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [1.2.0] - 2026-11-21

### 新增

- **菜单 5「检查更新」**：批量检查收藏仓库的最新 Release，展示上次/最新 tag 与更新摘要，结束后回写 tag 与资产缓存；内置无 Token 上限、>30 确认、低配额提前停止与 403/429 限流中断。
- **更新说明全屏查看**：搜索结果输入 `d` + 编号（如 `d3`）即可在新窗口查看该仓库 Release 的 Markdown 正文，↑/↓ 滚动、Q 返回，不跳转浏览器。

### 改进

- **rich 渲染界面**：表格、横幅与进度条改用 rich，自动列宽与中文/emoji 对齐更稳；更新说明由 rich Markdown 排版。
- **truststore 信任系统证书**：用 `truststore.inject_into_ssl()` 替代手写证书导出合并，开代理不再报 SSL 错误；已设 `REQUESTS_CA_BUNDLE` 时不覆盖。
- **downloader 重写为 asyncio + httpx**：删掉 threading/ThreadPoolExecutor/Lock，测速与分段下载改用 `asyncio.gather`；进度条交给 rich，代码量比原先少 30%。新增 `httpx` 依赖（`requests` 仍用于 GitHub API）。

## [1.1.1] - 2026-11-21

### 新增

- **Windows 安装版（Inno Setup）**：提供 `GHDownloader-Windows-V1.1.1-Setup.exe`，双击安装，
  自动创建桌面/开始菜单快捷方式，在「已安装的应用」中注册卸载项。无需 Python。
- **便携版重新打包**：主程序由 `ghfind.exe` 更名为 `GH Downloader.exe`，
  统一使用自定义应用图标（深色终端风格 + 绿色下载箭头）。
- **命令行下载入口**：README 与官网均提供 `wget` 一行命令直接下载安装版。
- **Winget 分发**：已提交 `netuser2011.GHDownloader` 至 `microsoft/winget-pkgs`，
  合并后可通过 `winget install netuser2011.GHDownloader` 安装。

### 改进

- 官网（GitHub Pages）主按钮改为直接下载安装版，不再跳转 Release 页面。
- README「安装」章节重写：安装版 / 便携版放前面，源码运行降为开发者选项。
- 版本标识统一为 v1.1.1，消除之前 V1.0.0 / V1.1.0 混用问题。

---

## [1.1.0] - 2025-06-15

### 新增

- **断点续传**：下载中断（断网 / Ctrl+C）不再删除半截文件，而是用 `.part` +
  `.part.meta` 记录已完成的字节与分段，下次重跑同一个下载只补未完成的部分。
  URL、总长、ETag / Last-Modified 任一不符就从头下载，避免文件更新后串味。
  永久性失败（HTTP 错误、返回网页、字节数不符）仍会清理干净。
- **无资产时的网页跳转**：Release 没有资产时不再只打印一句话就结束，而是列出
  Release 发布页、GitHub 仓库主页和作者填的项目官网供跳转；搜索选中仓库后也会
  先问一句是直接下载还是去网页看看。
- **自动信任系统证书**：启动时把 certifi 与 Windows 系统证书（含 Watt Toolkit /
  SteamTools 等代理工具装的根证书）合并去重，写到 `~/.gh-release-helper/ca-bundle.pem`
  并设置 `REQUESTS_CA_BUNDLE`，开着代理工具也不再报 SSL 错误。只用标准库 `ssl`，
  不新增依赖；已设置该环境变量时不覆盖，导出失败静默降级。主菜单状态行显示证书状态。
- **终端下载多线程分段**：文件 ≥ 2 MB 且服务器支持 `Range` 时切成 4 段并发下载
  （`GHR_THREADS` 可调到 1-8，超出会夹住）。各段只写自己那段偏移，收尾按总字节数核对；
  任何一段失败或字节数对不上，都删掉 `.part` 重新来过，不会留下半截安装包。
- **7 条线路与自动测速**：白名单 `downloader.MIRRORS` 里放 1 条直连 GitHub + 6 个公共镜像
  （`ghproxy.net`、`gh-proxy.com`、`ghfast.top`、`gh-proxy.org`、`gh-proxy.eu.org`、
  `ghp.keleyaa.com`），全部强制 `https://`，终端不接受临时输入的镜像地址。选自动测速时
  每条并发拉前 128 KB 比吞吐，表格按快慢排序并标出「◀ 已选中」；手动指定某条则跳过测速直接走。
  一条都不通时把 7 条各自的失败原因逐行列出，而不是闷头等到超时。
- **测速是并发跑的**：七条线路串行测最坏要等 7 × 超时，界面像卡死；改成一起发，
  整体只等 8 秒左右，没返回的线路记成「测速超过 N 秒未返回」，剩下的照常参与比较。
- **`downloader.fetch()`**：终端下载的统一入口，自己决定走多线程还是退回单流，
  返回（文件, 实际方式），界面层不再关心分段细节。

### 变更

- **下载方式从四项减成三项**：终端下载到本地 / 唤起浏览器下载 / 只打印下载链接。
  原来第一项是「唤起浏览器 + 本地直接下载」，同一个文件要下两遍——
  有 issue 说这是成事不足败事有余，现在一项只做一件事。
- 原「只下载到本地」升级为带测速与并发的终端下载，因此不再需要单独的选项；
  「只用浏览器打开」和「只打印链接」保留为第 2、3 项。

### 安全

- 镜像前缀强制 `https://`，线路 id 只认白名单，终端不接受临时输入的镜像地址。
  走镜像时文件确实经过第三方服务器、理论上可被替换，这一取舍在 README 与 SECURITY
  里都写明了；默认仍是直连，任何时候都能手动指定。
- 系统证书信任只纳入这台电脑**已受信任**的 CA（等价于浏览器的信任决策），
  不降低安全基线；bundle 写到用户自己的 `~/.gh-release-helper/`，
  不写程序目录、不写死本机路径，打包后分发到别的电脑也能各自独立工作。
- 断点续传的 `.meta` 记录 URL / 总长 / ETag，文件更新后不复用旧进度，
  避免把新文件的内容写到旧文件的偏移上。

## [1.0.0] - 2026-11-17

第一个可以公开发布的版本：从「拿链接」升级到「在终端里把整件事办完」。

### 新增

- **交互式主菜单**：`1 搜索仓库 / 2 查看收藏 / 3 添加收藏 / 4 退出` 四项，全程编号操作，
  不需要记住任何命令行参数。
- **按名字搜索仓库**：只输入仓库名关键词，GitHub Search API 按星标排序列出候选
  （作者/名字、星标、语言、简介），输入编号即可选中，不用再先查作者是谁。
- **收藏夹持久化**：以 `作者名/仓库名` 为键写入 `favorites.json`，同时记下星标、简介、
  最近一次看到的 tag 与资产清单；`owner` 或 `repo` 大小写不同也视为同一条，不会重复。
- **两种下载方式**：`webbrowser` 唤起系统默认浏览器，和 `requests` 流式直接落盘（带
  百分比 / 速度 / 剩余时间的单行进度条），也可以只用浏览器或只打印链接。
- **下载目录可选**：下载前四选一——用当前默认目录、仅本次换目录、换目录并永久记住
  （写进 `config.json`）、恢复系统默认下载目录；路径支持 `~` 与相对路径。
- **按类型筛选**：先问 ZIP 还是 EXE，其余类型（MSI、DMG、DEB、AppImage…）按资产里实际
  出现的扩展名动态补上，最后一项永远是「全部」。
- **命令行模式 `cli.py`**：不进菜单，一条命令打印全部链接，支持 `--ext`、`--no-latest`、
  `--limit`、`--token`、`--token-url`。
- **一步直达**：`python main.py files-community/Files` 直接进资产页；
  `python main.py files` 先搜索再选编号。
- **Token 引导配置**：首次运行无 Token 时会问一句，粘贴后写入本地 `.github_token`
  （POSIX 下权限 600），源码里不出现任何真实 Token。
- **菜单 `0` 一键跳到 Token 页面**：打印 GitHub 官方创建页地址（链接里已带上
  `scopes=public_repo&description=gh-release-helper`），确认后交给系统浏览器打开；
  粘贴回来只存本地 `.github_token`，屏幕上不再回显一遍，本次运行立即生效不用重启。
  细粒度 Token 页面和撤销页面的地址也一并给出来。
- **`python cli.py --token-url`**：不进菜单也能拿到创建页地址，远程帮别人排障时用得上；
  这条只打印地址，不读也不写 Token。
- **限流提示照着做就行**：`API 调用已达上限` 现在直接附上可点开的 Token 页面链接和
  「菜单里按 0」，不再只说一句「配置 Token 可提升限额」。
- **`Run.bat`**：双击启动。先把控制台切到 UTF-8、切到脚本所在目录，再自己找一个能用的
  Python（`py -3` 优先、`python` 兜底，都靠运行时判断 `errorlevel`），`requests` 缺失时按
  `requirements.txt` 补装，最后 `pause` 停窗。文件本身刻意只写 ASCII，中文提示全部由
  Python 打印。
- **离线单元测试**：`tests/` 下 100+ 个用例，不联网、不碰项目里的个人文件，
  `python -m unittest discover -s tests` 一句跑完。

### 修复

- **中文 Windows 控制台闪退**：控制台默认代码页 cp936（GBK），打印 emoji 会抛
  `UnicodeEncodeError` 直接退出。启动时把标准输出/错误重设为 UTF-8
  （`errors="replace"` 兜底），彻底消除这一类崩溃。
- **报错一闪而过**：
  - 主流程抛异常后立刻重画菜单，而重画的第一件事就是清屏，错误信息出现的同一瞬间被抹掉。
    现在错误会作为提示条在清屏之后重新贴回菜单顶部，看完之前不会被刷掉。
  - Python 版本过低、`requests` 未安装这两类早期失败，原来走 `sys.exit(消息)`，双击运行时
    窗口和消息一起消失。现在统一由 `bootstrap.py` 打印说明、写入 `crash.log`、等用户按键。
  - 任何没预料到的异常都会打印完整 traceback、追加进 `crash.log`，并要求按回车才退出。
- **表格错位**：中英文与 emoji 混排时按显示宽度（东亚全角字符与 emoji 记 2 列）对齐。
- **`NO_COLOR=0` / `FORCE_COLOR=0`** 被当成「开启」处理；现在只认非零值。
- **保存失败留下临时文件**：`favorites.json` 与 `config.json` 的原子写入在失败时清掉
  `.tmp`，不再留下垃圾文件。
- **命令行模式下 Ctrl+C 甩 traceback**：改为可读提示，退出码 130。
- **无效菜单编号要白按一次回车**：现在只重画菜单，直接回车也当作刷新。
- **`Run.bat` 里 `where python` 兜底不生效**：`if errorlevel 1 (...)` 块内写 `%errorlevel%==0`
  时，变量在解析阶段就被替换成固定值，运行时判断的其实是旧码。改成标签跳转 +
  运行时 `if errorlevel 1 goto`，Python Launcher 不存在时能正确落到 `python`。
- **`Run.bat` 里的中文把命令行劈开**：`chcp 65001` 之后 cmd.exe 按字节偏移重读批处理，
  含中文的行会从中间断开，后半截被当成命令执行（实测出现 `'往' is not recognized as an
  internal or external command`，以及 `rlevel` / `ython` / `fined` 之类的碎片）；另一行中文
  `echo` 还把 ERRORLEVEL 留在 1，于是「依赖安装失败」分支凭空触发。现在整个文件只用
  ASCII，中文提示一律由 Python 输出，并用 `.editorconfig` 锁定 CRLF。

### 安全

- Token 一律来自外部（`--token` > 环境变量 `GITHUB_TOKEN` > `.github_token`），
  三个个人数据文件全部写进 `.gitignore`。
- 菜单 `0` 与首次启动的引导都不会把用户粘贴的 Token 再打印一遍，也不写进 `crash.log`；
  它打开的是 GitHub 官方页面，链接里只有权限范围和本项目名字，不含账号或本机信息。
- 发布文档里不再出现本机用户名和家目录绝对路径：`PUBLISHING.md` 的路径统一写成
  `你的路径/gh-release-helper`，`icacls` 示例改用 `$env:USERNAME`，
  测试与工具缓存目录补进 `.gitignore`。
- 资产文件名做净化：只取最后一段并剔除非法字符，`../../etc/passwd` 这类恶意名字只会
  变成目录里的 `passwd`，无法路径穿越。
- 下载先写 `.part`，校验字节数一致后再改名；中断、超时、Ctrl+C 都会删掉半截文件。
- 移除面向特定下载工具的措辞，改为通用的「只打印下载链接，你可以粘到任何下载工具」。

### 已知限制

- `releases/latest` 不含草稿与预发布：作者只发预发布时会 404，请用
  `python cli.py owner/repo --no-latest`。
- 部分项目（如 VS Code）只发布 tag，安装包放在自己官网，资产列表会是空的。
- 本机若有 HTTPS 中间人代理（SteamTools、Charles、企业网关），SSL 校验会失败，
  需要把它的根证书通过 `REQUESTS_CA_BUNDLE` 交给 requests，详见 README 常见问题。

[Unreleased]: https://github.com/netuser2011/gh-release-helper/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/netuser2011/gh-release-helper/releases/tag/v1.0.0
