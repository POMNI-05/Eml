# Mac 日常使用：Google Workspace + 云模型复制粘贴

适用于公司邮箱由 Google Workspace 托管、平时使用 Legacy Outlook 或 Gmail 网页的单用户。
Eml 在这台 Mac 上启动，直接读取授权的 Gmail 邮箱。日常使用无需 Ollama 或 Gemini API key。

## 首次安装

1. 将项目下载到固定文件夹，例如 `~/Applications/Eml`；不要放在临时下载解压目录后又移动/删除。
   不要复制其它电脑的 `.venv`、token 或客户数据库。
2. 安装 Python 3.11 或以上，在终端运行 `python3 --version` 核对。
3. 双击 `Setup.command`，等待出现 `Setup complete`。
4. 双击 `Launch.command`，浏览器会打开 `http://127.0.0.1:8501`。
   使用期间保留终端窗口；可给 Launch 创建桌面替身，结束时在终端按 Ctrl+C。

若下载后的 `.command` 无执行权限，在终端进入项目文件夹后运行：

```bash
chmod +x Setup.command Launch.command
./Setup.command
./Launch.command
```

如果系统阻止脚本打开，使用终端在已确认的项目目录执行：
`python3 helpers/setup_local.py`，然后 `.venv/bin/python helpers/launch_local.py`。

## 公司邮箱授权

请公司管理 Google Cloud 项目，启用 Gmail API，创建 **Desktop app** OAuth 客户端，
下载 JSON 并在 Eml 首页上传。点击 **Connect Gmail**，在同一台 Mac 的浏览器选择老板自己的公司账号。
确认 Eml 显示的邮箱正确后再选邮件。详情见 [Gmail 设置](gmail_setup.md)。

只供同一 Workspace 组织内部使用时，让管理员确认项目归属并核对 **Audience → Internal** 是否适用。
公司邮箱后缀本身不能证明现有 OAuth 项目属于这个组织。管理员的第三方应用访问策略仍需允许 Eml。
[Google 官方配置说明](https://developers.google.com/workspace/guides/configure-oauth-consent)

若当前仍用 External + Testing，Gmail 范围的 refresh token 通常七天到期，需要重新授权。
三个月交接应先处理项目配置，再用实际账号验证；Internal 也不保证授权永不失效。
[Google token 说明](https://developers.google.com/identity/protocols/oauth2)

## 每次制作工作记录

1. 打开 **Launch.command**，连接 Gmail，选择/新建客户。
2. 在 **Client & scope** 选择日期和 Gmail 文件夹，或用 Client search 找邮件。
   这是首选路径，读取邮件不依赖 Outlook 正在运行。
3. 在 **Review emails** 检查正文、回复与附件，排除无关邮件，然后 **Use selected emails →**。
4. 在 **Draft & export** 保存写作偏好和必要的替换规则，点击 **Prepare prompt + emails for GPT**。
5. 展开 **Inspect the complete outgoing request**，确认脱敏结果，然后勾选审阅确认。
   点击 **Copy prompt + emails for GPT**，粘贴到公司获准的云模型服务。
   复制失败时点击 **Download prompt + emails**，打开下载的文本再复制。
6. 将模型返回的纯 JSON 保存为 `.json` 文件，通过 **Upload cloud response JSON to restore locally** 上传，
   点击 **Restore and save response**。文件须是纯文本，不是 RTF，也不要附带 Markdown 代码围栏或解释文字。
   若使用 Mac 文本编辑器保存，确认格式为纯文本且实际扩展名为 `.json`。
7. 检查还原后的名称、邮件引用、工作状态和措辞，填写审核人并保存，下载 **Word record**。
   模型返回格式不符合要求时，按界面错误修正返回内容，不修改包 ID 或捏造证据。

准备请求和本地还原不自动调用云模型。正常流程不需要展开 Gemini 设置或提供 API key。
保留待处理包直到返回结果成功导入；映射保存在本机数据库中。

## Legacy Outlook 的位置

老板可以继续用 Legacy Outlook 收发邮件。Eml 的 **Outlook selection (Mac)** 是可选入口：
读取选中邮件的 Internet Message-ID，再去同一个 Gmail 账号定位邮件。
需要在目标 Mac 上验证 AppleScript 与 Outlook 的自动化访问，不能用 Windows 测试代替。

只存在于 Outlook **On My Computer** 的邮件，或尚未同步到 Gmail 的内容，无法通过 Gmail 定位；
Smart Folder 也不等同于 Gmail 标签。交付当天先走 Eml 的 Gmail 文件夹/搜索流程，再检查 Outlook 选信。

## 重启、备份与排查

客户、草稿、待处理包和授权保存在 `~/Library/Application Support/Eml/`。
关闭应用后下次打开 Launch，连接同一账号和客户，可继续使用 Saved drafts 和待处理包。
不用重新安装，也不需要开发者电脑在线。

停止 Eml 后，向公司已有的私有备份文件夹保存一个新 ZIP：

```bash
.venv/bin/python helpers/backup_local.py --output "/path/to/private-backups/eml-2026-11-17.zip"
```

替换为真实的备份位置与当日文件名；程序拒绝覆盖已有 ZIP。
备份含原始资料、映射和授权，没有 ZIP 加密。恢复步骤见[安装指南](local_install.md#备份恢复与升级)。

故障排查：`.venv/bin/python helpers/launch_local.py --check`。
端口占用时先找到已有窗口；需要另一个端口可用 `--port 8502`。
不要同时运行多个实例写同一数据库。授权过期时重新连接，不要删除客户数据库。

交接前必须在老板的 Mac 上完成：实际邮箱授权、测试邮件与附件、复制/导入、Word 打开、重启恢复和备份恢复。
当前自动化和浏览器验证来自 Windows；尚不能作为这台 Mac 的现场验收记录。
