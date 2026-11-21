# GH Downloader v1.2.0

> 终端里的 GitHub Release 下载助手 —— 搜索、收藏、一键下载。

本版为 **功能更新版**：新增「批量检查更新」与「更新说明全屏查看」，界面改用 rich 渲染，
下载核心重写为 asyncio + httpx，并用 truststore 自动信任系统证书。安装版与便携版同步更新。

---

## 下载

| 文件 | 说明 |
| --- | --- |
| `GHDownloader-Windows-V1.2.0-Setup.exe` | **推荐。** 安装版，双击运行，自动配置快捷方式与卸载项 |
| `GHDownloader-Windows-V1.2.0.zip` | 便携版，解压后直接运行 `GH Downloader.exe`，无需安装 |

两种文件均无需安装 Python。安装版与便携版功能完全一致。

### 命令行下载（wget / curl）

```bash
# 安装版（Windows）
wget "https://github.com/netuser2011/gh-release-helper/releases/download/v1.2.0/GHDownloader-Windows-V1.2.0-Setup.exe"

# 便携版
wget -O ghdownloader.zip "https://github.com/netuser2011/gh-release-helper/releases/download/v1.2.0/GHDownloader-Windows-V1.2.0.zip"
```

---

## 本版变更

### 新增

- **菜单 5「检查更新」**：批量检查收藏仓库的最新 Release，表格对比上次/最新 tag 与更新摘要，带限流保护（无 Token 上限 40 个、403/429 自动停止）。
- **更新说明全屏查看**：搜索结果里输入 `d` + 编号（如 `d3`）打开新窗口，rich Markdown 排版，↑/↓ 滚动、Q 返回，不跳浏览器。

### 改进

- **rich 渲染界面**：表格、横幅与进度条改用 rich，自动列宽，中文/emoji 对齐更稳。
- **truststore 信任系统证书**：启动时注入系统证书存储，开代理工具不再报 SSL 错误，无需手动导出 PEM；已设 `REQUESTS_CA_BUNDLE` 时不覆盖。
- **downloader 重写为 asyncio + httpx**：删掉 threading/Lock/ThreadPoolExecutor，测速与分段下载改用 `asyncio.gather`，进度条交给 rich，代码量比原先少 30%；断点续传、多线路测速、文件名净化等行为保持不变。

### 依赖变化

- 新增 `httpx`（下载与测速）、`rich`（界面与 Markdown）、`truststore`（系统证书）；`requests` 仍用于 GitHub API。共 4 个第三方库，`pip install -r requirements.txt` 一句装齐。

---

## 安装说明

**安装版（推荐）：**

1. 双击 `GHDownloader-Windows-V1.2.0-Setup.exe`
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

需要 Python 3.10+ 和 `requests` / `httpx` / `rich` / `truststore`：

```bash
git clone https://github.com/netuser2011/gh-release-helper
cd gh-release-helper
pip install -r requirements.txt
python main.py
```

---

完整更新日志见 [CHANGELOG.md](https://github.com/netuser2011/gh-release-helper/blob/main/CHANGELOG.md)。有问题欢迎提 Issue。
