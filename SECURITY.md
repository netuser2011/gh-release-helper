# 安全政策

## 这个工具会碰你的什么

| 数据 | 位置 | 是否提交到 Git |
| --- | --- | --- |
| GitHub Token | `.github_token`（POSIX 下权限 600） | 已 `.gitignore` |
| 收藏清单 | `favorites.json` | 已 `.gitignore` |
| 下载目录偏好 | `config.json` | 已 `.gitignore` |
| 崩溃记录 | `crash.log` | 已 `.gitignore` |

网络出口只有两个：`api.github.com`（读接口）和 `github.com`（下载资产、唤起浏览器）。
没有统计、没有埋点、没有自动更新、没有任何写操作（只用 `GET`，权限上等同于只读）。

## Token 的使用方式

- 源码里没有任何真实 Token，也永远不会有。取值顺序固定为
  `--token` 参数 > 环境变量 `GITHUB_TOKEN` > 本地 `.github_token` 文件。
- Token 只出现在发给 `api.github.com` 的请求头里（`Authorization: Bearer …`）。
- 配置入口（菜单里的 `5`、首次启动的引导）只做三件事：打印 GitHub 官方的
  Token 创建页地址、把它交给系统默认浏览器、把你粘贴的内容写进 `.github_token`。
  粘贴的 Token 不会在屏幕上回显，也不会进 `crash.log`；打印出来的链接只有
  `scopes=public_repo` 和本项目名字，不含账号信息或本机路径。
- 不想在这台机器上留 Token：直接删掉 `.github_token`，程序会退回匿名模式
  （60 次/小时），下次按 `5` 可以再配。想彻底作废，去下面的撤销页面 revoke。
- 建议只授予默认的最小范围（公开仓库甚至不需要任何 scope）。
- **如果 Token 不小心被提交、粘贴进 issue 或聊天记录**：把它当成已经泄露处理，
  立刻到 <https://github.com/settings/tokens> 撤销并重新生成，然后把本地
  `.github_token` 换成新的。撤销只需要一分钟，代价远小于事后补救。
- 检查历史是否干净：`git log --all --stat -- .github_token` 应该没有任何输出。

## 下载相关的防护

- 资产文件名会先净化：只保留最后一段路径，剔除 `< > : " / \ | ? *` 和控制字符，
  空名字回退为 `release-asset`，长度截到 150 字符。`../../etc/passwd` 只会变成目标目录里的
  `passwd`，无法写到目录之外。
- 同名文件不覆盖，自动加 `(1)`、`(2)`。
- 先写 `.part`，字节数与 `Content-Length` 一致后才改名；长度不符、响应是 HTML 页面、
  Ctrl+C、连接中断都会删掉临时文件，不留一个「看着完整其实打不开」的残文件。
- 只信任 API 返回的 `browser_download_url`。若某个 release 的资产被人替换，
  GitHub 侧的链接也会跟着变——这一层信任的是 GitHub，请照常用官方域名核对。

## 报告漏洞

请不要直接开公开 issue。优先用 GitHub 的私密安全报告入口：
仓库页 → **Security → Report a vulnerability**（需要维护者在
Security → Advanced Security 里开启）。

若该入口尚未开启，可先发一个只写「发现安全问题，详见附件」的空 issue 引起注意，
或在 <https://github.com/netuser2011/gh-release-helper/issues> 里留言，
维护者会用私密方式跟进。

## 已知不构成漏洞的行为

- 用 `os.system("")` 只是为了让 Windows 控制台启用 ANSI 转义序列，不执行任何用户输入。
- `Run.bat` 会 `chcp 65001` 改代码页，只影响当前那个命令行窗口。
- 「唤起浏览器」就是把链接交给系统默认浏览器，不注入脚本、不静默下载。
