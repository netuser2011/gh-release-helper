# GH Downloader v1.3.0

> 终端里的 GitHub Release 下载助手 —— 全屏交互、按类型筛选、一键下载。

本版为 **大功能更新版**：界面升级为 Textual 全屏 TUI，资产按后缀分组筛选，下载完自动运行安装包或解压，链接可复制，收藏可删除，并修复了进度条与「只打印链接」等一系列问题。

---

## 下载

| 文件 | 说明 |
| --- | --- |
| `GHDownloader-Windows-V1.3.0-Setup.exe` | **推荐。** 安装版，双击运行，自动配置快捷方式与卸载项 |
| `GHDownloader-Windows-V1.3.0.zip` | 便携版，解压后直接运行 `GH Downloader.exe`，无需安装 |

两种文件均无需安装 Python。安装版与便携版功能完全一致。

### 命令行下载（wget / curl）

```bash
# 安装版（Windows）
wget "https://github.com/netuser2011/gh-release-helper/releases/download/v1.3.0/GHDownloader-Windows-V1.3.0-Setup.exe"

# 便携版
wget -O ghdownloader.zip "https://github.com/netuser2011/gh-release-helper/releases/download/v1.3.0/GHDownloader-Windows-V1.3.0.zip"
```

---

## 本版变更

### 新增

- **Textual 全屏 TUI**：搜索、仓库、资产、下载、收藏、更新说明全部改为可点击/方向键操作的全屏页面，网络请求放后台，界面不卡。
- **按类型分组筛选**：Release 资产先按 ZIP / EXE / TAR / APK / MAS / KMASIX 等后缀分组，选类型后再列具体文件，不再一次刷出几十条链接。
- **下载方式三按钮**：终端下载 / 浏览器下载 / 只打印链接，点一下即可，不用再输 1/2/3。
- **下载进度与测速可视化**：展示 7 条线路测速结果与自动选中的线路，下载中用进度条 + 实时速度显示。
- **下载后处理**：安装包下载完弹窗询问是否直接运行；zip 自动解压并询问是否删包。
- **可复制的链接页**：只打印链接时打开独立页面，输入框可框选复制，也有复制按钮与反馈。
- **收藏删除**：二次确认后删除并刷新列表与计数。
- **统一返回按钮**：所有页面都有「← 返回上一级」按钮，ESC 仍可用。
- **mypy 类型检查**：CI 增加渐进式类型检查，先覆盖四个核心模块。

### 改进

- **下载提速与稳定性**：测速不再把首字节延迟误算成吞吐；默认并发提升到 8 路（上限 16），分段门槛降到 512 KB，读取块增大到 256 KB 并跳过解码层；并发被限制时自动回退单流，不再直接失败。

### 修复

- 全屏界面下下载进度条被吞、完成后看不到速度的问题。
- 「只打印下载链接」点击后没有任何输出的问题。
- 搜索结果出来后不能直接回车进入仓库页的问题。
- 弹窗覆盖时刷新状态行抛异常导致后台任务报错的问题。

---

## 安装说明

**安装版（推荐）：**

1. 双击 `GHDownloader-Windows-V1.3.0-Setup.exe`
2. 按向导选择安装路径（默认 `C:\Program Files\GH Downloader`）
3. 完成后桌面出现快捷方式，开始菜单同步创建
4. 卸载：设置 → 应用 → 已安装的应用 → 搜索 "GH Downloader" → 卸载

**便携版：**

1. 解压 ZIP 到任意目录
2. 双击 `GH Downloader.exe` 即可运行
3. 删除该目录即为卸载，无残留

> 注意：`GH Downloader.exe` 与 `_internal/` 文件夹需保持在同一目录，不要单独移动 exe。

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
