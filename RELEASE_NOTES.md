# GH Downloader v1.3.2

> 终端里的 GitHub Release 下载助手 —— 全屏交互、按类型筛选、多线路择优、一键下载。

本版为 **稳定性与数据迁移版本**：修掉缺依赖提示的占位符、分段下载失败被误判成「用户中断」、自更新还没装完就改写版本号等 11 处问题；同时把 Token / 收藏 / 配置搬到 `%APPDATA%`，装在 Program Files 后也能正常保存，卸载不再丢数据。

---

## 下载

| 文件 | 说明 |
| --- | --- |
| `GHDownloader-Windows-V1.3.2-Setup.exe` | **推荐。** 安装版，双击运行，自动配置快捷方式与卸载项 |
| `GHDownloader-Windows-V1.3.2.zip` | 便携版，解压后直接运行 `GH Downloader.exe`，无需安装 |

两种文件均无需安装 Python，功能完全一致。

### 命令行下载（wget / curl）

```bash
# 安装版（Windows）
wget "https://github.com/netuser2011/gh-release-helper/releases/download/v1.3.2/GHDownloader-Windows-V1.3.2-Setup.exe"

# 便携版
wget -O ghdownloader.zip "https://github.com/netuser2011/gh-release-helper/releases/download/v1.3.2/GHDownloader-Windows-V1.3.2.zip"
```

已经是 v1.3.1 的话不用手动下载：打开程序 → 菜单 `4`「检查更新」，确认后会自动下载安装包并升级。新版本号以安装包自带的 `version.txt` 为准，没真正装完不会显示「已最新」。

---

## 本版变更

### 修复

- **缺依赖提示出现字面量 `%s`。** 启动检查算出了缺失模块却没填进提示语，用户和 `crash.log` 里都看到「缺少第三方依赖：%s」。现在显示真实模块名，例如「缺少第三方依赖：no_such_mod_xyz」。
- **分段下载失败被当成「用户中断」，永远不回退单流。** 镜像限流、代理 reset 这类网络层中断现在单独归类：清掉 `.part` 残片后自动改用单流重试；只有你主动按 Ctrl+C 才保留进度、不回退。
- **清理 `.part` 时被杀软 / 索引占用顶成裸 traceback。** 删除临时文件遇到 `PermissionError` 不再盖住真正的下载错误，删不掉的文件留到下次启动再清。
- **自更新在安装前就改写 `version.txt`。** 静默安装刚启动、或从安装目录运行只提示「请手动运行」时，版本号就被提前写新，导致后续「检查更新」永远说已最新。现在只有新包自带的 `version.txt` 才生效。
- **仓库深链接被当成关键词搜索。** `https://github.com/o/r/releases/tag/v1`、`.../tree/main` 这类地址现在直接归一化成 `o/r` 进入该仓库流程，查询串与 `#` 片段也会被剥掉。
- **TUI 在后台线程改收藏并写盘。** 20 个仓库的检查结果现在只收集在内存里，回到主线程一次性 `update_release` + `save`，并刷新状态行，避免和删收藏、退出保存竞态或留下 `.tmp`。
- **带扩展名的保留设备名挡不住。** `CON.txt`、`NUL.log`、`COM1.zip` 现在按扩展名前第一段判断，自动加下划线；`console.log` 不受影响。
- **勾叉符号把表格撑歪。** `✓✔✕✖` 在终端里只占一列，不再按两列算；行比表头多一格时也不会抛 `IndexError`。

### 改进

- **用户数据搬到 `%APPDATA%`。** Token、收藏、下载目录偏好分别落在 `%APPDATA%\gh-release-helper\`（非 Windows 是 `~/.local/share/gh-release-helper/`），可用 `GHR_DATA_DIR` 覆盖。源码目录里已有的三个文件会在首次启动时自动复制过去，旧文件保留；`version.txt` 仍在程序目录，供安装包覆盖。
- **高速线路下载时进度回调节流。** 距上次推送不足 0.1 秒的中间帧不再做跨线程同步往返；完成帧强制推送，进度条一定走到 100%。
- **清理死代码。** 删掉 TUI 里三个无引用的导入，类型检查与测试保持全绿。

---

## 安装说明

**安装版（推荐）：**

1. 双击 `GHDownloader-Windows-V1.3.2-Setup.exe`
2. 按向导选择安装路径（默认装到当前用户的程序目录）
3. 完成后桌面与开始菜单各有一个快捷方式
4. 卸载：设置 → 应用 → 已安装的应用 → 搜索 "GH Downloader" → 卸载

**便携版：**

1. 解压 ZIP 到任意目录
2. 双击 `GH Downloader.exe` 即可运行
3. 删除该目录即为卸载，无残留

> 注意：`GH Downloader.exe` 与 `_internal/` 文件夹需保持在同一目录，不要单独移动 exe。
> `_internal\version.txt` 是版本号的唯一真相源，删掉它程序会认为自己是 `V0.0.0` 并一直提示更新。
> Token / 收藏 / 配置不在程序目录里，升级或卸载都不会动它们；想整体迁走就复制 `%APPDATA%\gh-release-helper\`。

---

## 从源码运行

需要 Python 3.10+ 和 `requests` / `httpx` / `textual` / `truststore`：

```bash
git clone https://github.com/netuser2011/gh-release-helper
cd gh-release-helper
pip install -r requirements.txt
python main.py
```

---

完整更新日志见 [CHANGELOG.md](https://github.com/netuser2011/gh-release-helper/blob/main/CHANGELOG.md)。有问题欢迎提 Issue。
