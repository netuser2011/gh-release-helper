# 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循
[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

（下一个版本待补充的内容写在这里。）

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
