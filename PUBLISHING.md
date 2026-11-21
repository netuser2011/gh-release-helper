# 发布到 GitHub：完整步骤

从「本地一个文件夹」到「别人能 clone、能装、能提 issue 的公开仓库」，按顺序做完即可。
命令都在 Git Bash 或 PowerShell 里跑（`git` 已装好：2.52）。

文中一律用 `netuser2011` 作为 GitHub 用户名——它取自本机 `git config user.email` 里
`@` 前面那段（noreply 地址要去掉开头的数字 ID 和加号）。仓库地址、CI 徽章、
更新日志对比链接、issue 模板的联系方式都写的是这个名字；公开文档里只需要用户名，
不要把你的邮箱地址、用户 ID 或本机路径一起放进去。如果这个用户名不对，全局替换一次即可：

```bash
sed -i 's/netuser2011/你的用户名/g' PUBLISHING.md CHANGELOG.md SECURITY.md \
    .github/ISSUE_TEMPLATE/config.yml

# 换完确认没有残留（下面这条应该没有输出）
grep -rn "netuser2011" . --include="*.md" --include="*.yml" | grep -v "^./.git/"
```

`.github/ISSUE_TEMPLATE/bug_report.md` 里的 `https://github.com/<owner>/<repo>/releases/latest`
**故意**保留尖括号：那是提问者在描述自己要下载的那个仓库，不是本项目。

---

## 第 0 步：发布前必须确认的四件事

```bash
cd "你的路径/gh-release-helper"      # 就是这个文件夹本身，别在别的目录下跑

# 1) 个人数据与密钥都在忽略列表里
git check-ignore -v .github_token favorites.json config.json crash.log

# 2) 源码里没有任何 Token（应该只列出 README/SECURITY 里的说明文字，不含 ghp_ 开头的串）
grep -rn "ghp_[A-Za-z0-9]" --include="*.py" .

# 3) 文档与代码里没写死本机用户名（这条必须完全没有输出）
grep -rn "$(basename "$HOME")" --include="*.md" --include="*.py" --include="*.yml" --include="*.bat" .

# 4) 待提交清单里没有意外文件
ls -a
```

判定标准：

- 第 1 条四行都有输出（说明这四个文件不会被提交）。
- 第 2 条**必须没有任何 `.py` 文件的命中**。之前有一次把真实 Token 写进了源码，
  那个 Token 请确认已经在 <https://github.com/settings/tokens> 撤销；已经泄露过的 Token
  换掉比祈祷它没被人看到更省事。
- 第 3 条同理：绝对路径一律写成 `你的路径/gh-release-helper`，PowerShell 例子用
  `$env:USERNAME` 而不是真用户名；桌面路径、`C:/Users/…` 都不要进公开仓库。
- `.github_token` 里放的是真实 Token，公开发布前建议直接删掉（`rm .github_token`）：
  程序会退回匿名模式，需要解除限流时按菜单里的 `0` 会重新问一次，Token 只落回本地文件。
  决定留着的话它的权限通常是 `0666`，在 PowerShell 里收紧一下：
  ```powershell
  icacls .github_token /inheritance:r /grant:r "$env:USERNAME:F"
  ```

## 第 1 步：初始化仓库

```bash
git init -b main
git add .
git status          # 逐行看一遍：不该出现 favorites.json / .github_token / crash.log
```

`git add .` 之后如果 `git status` 里冒出了上面这几个文件，说明 `.gitignore` 没生效，
先别提交，回来检查。

## 第 2 步：首次提交

```bash
git commit -m "feat: GitHub Release 交互式下载助手 v1.0.0

终端里的四步菜单：搜索仓库、查看收藏、添加收藏、退出。
收藏以 作者名/仓库名 为键存进 favorites.json；下载支持浏览器唤起与
requests 流式落盘，保存目录可临时选也可永久记住。
全部走官方 REST API，只依赖 requests。"

git log --oneline
git show --stat HEAD
```

提交前把 `LICENSE` 第一行的版权持有人换成你自己的名字或 GitHub 用户名（可选，
`gh-release-helper contributors` 也是合法的）。想换成 Apache-2.0 或 GPL-3.0，
README 的 License 段落和这行要一起改。

## 第 3 步：在 GitHub 上建仓库

网页 → `+` → New repository：

| 项 | 建议值 |
| --- | --- |
| Repository name | `gh-release-helper` |
| Description | `在终端里搜索 GitHub 仓库、管理收藏、一键下载 Release 资产，只依赖 requests` |
| 可见性 | **Public** |
| Initialize this repository with a README | **不勾**（本地已有 README，勾了会产生冲突） |
| .gitignore / License | 都选 **None**（本地已带） |

也可以用命令行（需要先 `gh auth login`）：

```bash
gh repo create netuser2011/gh-release-helper --public \
  --description "在终端里搜索 GitHub 仓库、管理收藏、一键下载 Release 资产，只依赖 requests" \
  --source . --remote origin --push
```

## 第 4 步：推送

```bash
git remote add origin https://github.com/netuser2011/gh-release-helper.git
git remote -v
git push -u origin main
```

要输密码时，GitHub 不接受账号密码，需要用 Personal Access Token（classic，勾选 `repo`）
作为密码，或者改用 SSH 地址。Windows 的「凭据管理器」里存过旧密码的话，先删掉那条。

## 第 5 步：仓库设置（网页，五处）

1. **About**（右下角齿轮）
   - Description：填上面那句
   - Website：留空
   - Topics：`github-release` `download` `cli` `terminal` `python` `github-api`
     `release-assets` `windows-console` `interactive-cli` `favorites`
2. **README 顶部徽章**：CI 跑绿后加
   ```markdown
   ![CI](https://github.com/netuser2011/gh-release-helper/actions/workflows/ci.yml/badge.svg)
   ```
3. **Issues**：确认「Allow multiple issue templates」已开，`.github/ISSUE_TEMPLATE/`
   才会生效（新建 issue 时会问选哪个模板）。
4. **Security → Advanced Security**：打开 Private vulnerability reporting，
   SECURITY.md 里写的私密报告入口才可用。
5. **Settings → Branches**：给 `main` 加保护分支，要求 CI 通过才能合并（人少的时候可以跳过）。

## 第 6 步：检查 CI

推送后到 **Actions** 页面看两条 job：

- `离线单元测试 · Python 3.10 / 3.11 / 3.12 / 3.13`
- `Windows 控制台冒烟 · 报错不闪退`

全绿才算发布完成。第二条里有一条专门的检查：不设 `PYTHONUTF8` / `PYTHONIOENCODING`，
直接用系统默认编码走一遍菜单退出——这正是之前「双击闪退」的触发条件，改坏了就会变红。

## 第 7 步：打 tag，发 Release

```bash
git tag -a v1.0.0 -m "第一个公开版本：搜索 / 收藏 / 下载 / 报错不消失"
git push origin v1.0.0
```

网页 → Releases → Draft new release → 选 `v1.0.0`：

- **Release title**：`v1.0.0 终端里的 GitHub Release 下载助手`
- **Generate the changelog** 按钮先点一下，再手动整理成 CHANGELOG.md 里那段的摘要
- 这个工具本身是源码，**不需要上传二进制资产**；想上传也行，把
  `git archive` 出来的 zip 传上去：
  ```bash
  git archive --format=zip --prefix=gh-release-helper/ -o ../gh-release-helper-v1.0.0.zip HEAD
  ```

## 第 8 步：让别人找到它

README 第一屏已经写清了「不知道作者也能找」这个卖点，可以发去这些地方（按你自己的判断）：

- V2EX、Reddit `r/commandline`、`r/Python`、知乎/少数派
- `awesome-cli-apps`、`awesome-python` 之类的清单仓库提 PR

一句话介绍模板：
> 不知道作者是谁也能用——只输入仓库名就能搜出候选，按编号选，收藏常用项目，
> 然后浏览器 + 本地同时下载。纯终端，只依赖 requests。

## 发布后自检清单

- [ ] 用一台干净机器（或新建虚拟环境）跑：`git clone` → `pip install -r requirements.txt` → `python main.py`
- [ ] `双击 Run.bat` 能进菜单：它会自己找 Python（`py -3` → `python`），缺 `requests` 时自动
      按 `requirements.txt` 装一次；故意把 `GITHUB_TOKEN` 设成错的，报错要停在窗口里等你按键
- [ ] `Run.bat` 仍然是纯 ASCII：`grep -nP '[^\x00-\x7F]' Run.bat` 无输出，`file Run.bat` 里带 CRLF。
      这个文件一旦写进中文，cmd.exe 会按字节错位重读、把半句话当命令执行，别改
- [ ] 匿名状态下（删掉 `.github_token`）连搜 15 次，看限流提示是否明确
- [ ] Actions 全绿；徽章能显示
- [ ] 新 issue 页面能看到「问题反馈 / 功能建议」两个模板
- [ ] `git log --all -p -S "ghp_"` 无输出（确认历史里没有 Token）
