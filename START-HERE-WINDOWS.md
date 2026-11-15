# Windows 独立验证包

这是 `test/windows-parity` 分支，与 Mac 交付主线隔离。共享客户、Gmail、附件、脱敏、云包、审核与 Word 导出代码。
下载 ZIP 后先**全部解压**到固定文件夹，再运行；不要在 ZIP 预览里双击脚本。
本轮已完成全新安装、168 项测试及浏览器操作验证，详情见[验证记录](docs/windows_validation.md)。

## 马上试用

1. 电脑需有 **Python 3.11 或以上**，在终端运行 `py -3 --version` 或 `python --version` 核对。
   没有 Python 时先安装；这个包不包含 Python，也不是独立 `.exe` 安装器。
2. 双击 **Setup.cmd**，首次需联网下载依赖。看到 `Setup complete` 后继续。
3. 先双击 **Try-Demo.cmd**：使用虚构客户与邮件，不需要 Gmail 登录、OAuth 文件、模型账号或 API key。
4. 要测试自己的 Gmail / Google Workspace，关闭演示后双击 **Launch-Windows-Test.cmd**，
   上传自己的 Google Desktop OAuth JSON 并连接账号。参见 [Gmail 设置](docs/gmail_setup.md)。

`Launch.cmd` 在这个分支也会启动隔离测试模式。保留终端窗口，结束时 Ctrl+C。
这个版本不启动本地模型。日常主路径仍是复制脱敏包给公司获准的云模型，再导入返回 JSON。

## 演示完整流程

- 在 Email source 选 **Client folders (IMAP)**，关闭 **Filter by date**，点击 **Load folders**，选择 `Clients/Demo Consulting`。
- 点击 **Open selected folders →**，检查三封虚构邮件与附件；可排除 `news@software.example`。
- 点击 **Use selected emails →**，再点击 **Prepare prompt + emails for GPT**。
- 检查请求预览，勾选审阅确认，试用 **Copy prompt + emails for GPT**；复制受浏览器限制时使用下载按钮。
- 页面底部有 **Download synthetic response JSON**：下载后在上方上传并 **Restore and save response**。
  这是脚本返回值，只验证导入、还原和导出，不代表真实模型效果。
- 编辑描述、填写审核人、确认审核、保存，然后下载 Word 并打开。
- 关闭重开 Try-Demo，选择同一客户，进入 **3. Draft & export → Saved drafts** 打开保存的结果。

要测试实际云模型，使用已审阅的合成包复制粘贴，按包内要求返回 JSON，再上传到对应的待处理包。
演示的脚本返回值不验证云服务本身；真实 Gmail 登录只在正式测试入口验收。
如果使用个人 Gmail，OAuth 测试项目需允许这个账号（External + Testing 时添加到 Test users）；
公司 Internal 项目不能直接给组织外的个人 Gmail 授权。

## 隔离范围

| 内容 | Windows 测试版 |
| --- | --- |
| 真实账号测试地址 | `http://127.0.0.1:8521` |
| 合成演示地址 | `http://127.0.0.1:8522` |
| 真实测试资料与授权 | `%LOCALAPPDATA%\Eml-Windows-Test\workspace\` |
| 演示资料 | `%LOCALAPPDATA%\Eml-Windows-Test\demo\` |
| 测试备份 | `%LOCALAPPDATA%\Eml-Windows-Test\backups\` |

启动器覆盖其它 Eml 安装遗留的授权/数据库路径，不迁移已有资料，也不继承其它安装的 Gemini 环境变量 key。
不共享 Mac 主线数据目录。测试资料仍是本机文件，没有额外加密；浏览器账号会话与剪贴板不属于应用数据隔离。
借用电脑测试真实账号后，可在 **Gmail connected → Disconnect Gmail** 断开本机授权，
并按需要退出浏览器账号；该操作不自动删除已下载的邮件证据、草稿或系统下载文件。

双击 **Check-Windows-Test.cmd** 检查依赖、网络、授权文件元数据和测试数据库。
关闭工作区后双击 **Backup-Windows-Test.cmd**，生成新的测试 ZIP，不覆盖旧备份。
恢复见[安装指南](docs/local_install.md#备份恢复与升级)；测试启动器路径固定，恢复测试应使用指向新目录的标准 launch helper。

## 与 Mac 的对应关系

| 功能 | 状态 |
| --- | --- |
| Gmail 登录、文件夹、搜索、日期与选信 | 共用 Mac 主线代码；真实账号需在目标电脑授权验证 |
| 客户资料、文档及附件提取 | 共用代码 |
| 脱敏、复制/下载请求、JSON 还原 | 共用代码 |
| 来源审核、保存、Word 导出 | 共用代码 |
| 可选 Gemini API | 共用代码；仍需自己的 key/model/项目配置，本次不做真实计费调用 |
| Outlook 当前选中邮件 | Mac 为 AppleScript；Windows 新增 Classic Outlook COM 适配，需实机验证 |
| New Outlook for Windows | 不支持 COM 选信；使用 Gmail 文件夹、搜索或粘贴 Internet Message-ID |

Windows Outlook 适配只读取已经打开的 Classic Outlook 当前选择中的 Internet Message-ID，
不会启动新的 Outlook、修改或发送邮件。需与 Outlook 使用同一 Windows 用户和权限级别。
混入非邮件项目、缺 Message-ID、超时或没有选择时会报错，不静默使用部分选择。
选中的邮件仍必须存在于已连接的 Google 邮箱；这不是 Microsoft 365/Exchange 后端。

Microsoft 文档：[选信接口](https://learn.microsoft.com/en-us/office/vba/api/outlook.explorer.selection)、
[Message-ID 属性](https://learn.microsoft.com/en-us/office/client-developer/outlook/mapi/pidtaginternetmessageid-canonical-property)、
[新旧 Outlook 差异](https://support.microsoft.com/en-us/outlook/getstarted/feature-comparison-between-new-outlook-and-classic-outlook)。

自动化通过不等于舍友电脑上的实际安装、账号授权或 Outlook 已通过。测试时记录 Python 版本、
浏览器、是否 Classic Outlook，以及失败步骤；不要将 token 或完整客户邮件写入反馈日志。
