# B站视频下载器

适用于 Windows 10 / 11（64 位）的本地下载工具。界面在浏览器中打开，服务只监听本机 `127.0.0.1`；不需要部署服务器。下载引擎是 yt-dlp，音视频合并使用 FFmpeg。

**[下载 Windows 版](https://github.com/yangyu0929/bilibili_video_downloader/releases/latest)** · **[项目主页](https://yangyu0929.github.io/bilibili_video_downloader/)**

## 普通用户：无需安装 Python

1. 在 Releases 页面下载 `BilibiliDownloader-Windows-x64.zip`。
2. **解压整个文件夹**到有写入权限的位置，双击 `BilibiliDownloader.exe`。请保留旁边的 `_internal` 文件夹。
3. 浏览器会打开本地界面，粘贴链接并开始下载。

首次下载会自动准备 FFmpeg（约 31 MB，需联网），之后使用本机缓存。如已安装 FFmpeg，则直接使用。视频默认存放在 EXE 旁边的 `downloads` 文件夹。

## 开发者：从源码运行

1. 双击 `start.cmd`。首次运行会建立独立 Python 环境并联网安装依赖；需要 Python 3.10 或更新版本。
2. 等待浏览器打开。如果没有自动打开，复制启动窗口显示的完整网址到浏览器。
3. 粘贴 B站视频链接、b23.tv 短链接、分享文字或 BV 号。
4. 设置保存目录与清晰度，点击“开始下载”。默认文件保存在本程序的 `downloads` 文件夹。
5. 下载完成后界面会显示文件完整路径，可在资源管理器中打开对应目录。

请保持启动窗口打开。按 Ctrl+C 退出本地服务，并停止当前下载。取消会保留已下载的片段，再次下载相同视频时通常可续传。

## 支持范围

- 普通视频，以及账号能够访问的番剧播放页。
- 默认下载当前一 P；指定分 P 请使用带 `?p=2` 等参数的视频链接。不批量下载收藏夹或 UP 主投稿。
- 480P / 720P / 1080P 上限和最高可用画质。实际画质受视频源、登录状态、账号权限影响。
- 自动合并分开的音视频流为 MP4；源视频若已是完整单文件则保留源容器。
- 一个任务同时运行，支持进度、速度、错误日志和取消。

## 登录与高清

许多视频可以直接下载；部分高清格式、番剧等需要账号登录信息。在“登录凭证”中填写本人账号的 **Netscape 格式 cookies.txt 文件完整路径**。浏览器中复制的一行 Cookie 字符串不是此格式。需要时可使用自己信任的 Cookie 导出工具；程序不要求填写账号密码。

Cookie 等同于登录凭证，请仅在本机保管，不要发给别人或加入代码仓库。yt-dlp 可能更新该 Cookie 文件，因此应提供可写的导出副本。下载请求由本机直接发送至 B站及其视频分发服务。

程序不会提供超出账号权限的内容访问能力。仅用于下载自己拥有或获授权的内容。

## 常见问题

- **音画不同步 / 画面落后**：先用 VLC 或 mpv 播放同一个文件作对比。v1.0.1 起可选择“兼容优先”，在同分辨率下优先下载 H.264；实际格式见运行日志。源视频无相应 H.264 时会回退到其他编码，尤其是高分辨率视频。兼容版文件名带 `[compatible]`，不会因旧文件存在而跳过重下。此选项针对解码兼容问题，不保证修复源视频或时间戳导致的不同步。如果多个播放器均有固定偏移或逐渐增大的偏差，请反馈 BV 号、分 P、播放器及偏差表现；不要分享 Cookie。程序不擅自改变原始音频偏移或帧率。

- **403 / 412 / 请求受限**：先在浏览器确认视频可播放，稍后重试；必要时提供有效 Cookie。
- **清晰度较低**：登录凭证、账号权限或源视频限制；可尝试“最高可用”。
- **提示没有对应格式**：所选清晰度上限内可能没有可用格式，尝试“最高可用”。
- **Cookie 无效**：重新导出 Netscape 格式文件，确认路径和登录状态。
- **一直无法解析**：B站接口可能变化，可在程序目录运行以下命令更新引擎：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade yt-dlp
```

- **没有 Python**：从 https://www.python.org/downloads/ 安装 Python 3.10+，安装时勾选添加到 PATH，再双击启动。
- **启动安装失败**：检查网络，并在程序目录运行 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` 查看完整错误。

## 命令行启动与检查

```powershell
python launch.py
.\.venv\Scripts\python.exe app.py --no-browser
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

源码运行使用系统可用的 FFmpeg，否则使用 imageio-ffmpeg 自带的可执行文件。便携版不内置 FFmpeg，而是首次使用时从 PyPI 下载并校验 SHA-256，缓存到 `%LOCALAPPDATA%/BilibiliDownloader/tools/`。端口默认随机分配，也可用 `--port 8765` 指定。浏览器地址含有本次运行的随机访问令牌，请从启动窗口中的完整链接打开。

## 打包与 GitHub 发布

本目录应作为独立 GitHub 仓库的根目录。请勿上传 `.venv`、`downloads` 或个人 Cookie 文件。

本机打包：在 PowerShell 中运行 `powershell -ExecutionPolicy Bypass -File build.ps1`。脚本会安装构建依赖、运行测试、生成便携程序，并对 EXE 进行启动检查。产物是 `dist/BilibiliDownloader-Windows-x64.zip`。

GitHub 自动发布：

1. 将仓库默认分支设为 `main`，启用 Actions。
2. 推送版本标签，例如 `git tag v1.0.0` 后运行 `git push origin v1.0.0`。
3. `Build Windows release` 会在 Windows 环境测试、打包，并将 ZIP 发布到对应的 Release。
4. 也可在 Actions 中手动运行该工作流，直接下载构建产物；手动运行不创建 Release。
5. 可选展示页：在 Settings → Pages → Build and deployment 中选择 **GitHub Actions**，再手动运行 `Publish download page`。

新版本建议重新构建，以更新 yt-dlp 对 B站接口的兼容性。当前构建未使用代码签名证书。

本项目自身代码采用 MIT 许可，第三方组件见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
