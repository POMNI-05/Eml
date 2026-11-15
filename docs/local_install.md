# 本地安装、云端生成与交接

适用于 2026-11-17 交接用 `main`。程序在使用者电脑运行，不需要开发者电脑在线。
主线默认采用脱敏包复制/下载及可选 Gemini，不需要 Ollama。
完整验证状态与托管取舍见[交接记录](handoff_2026-11-17.md)。

## 首次安装与日常入口

先安装 Python 3.11 或以上，将项目下载到固定文件夹：

| 系统 | 首次安装 | 以后每次使用 |
| --- | --- | --- |
| Windows | 双击 `Setup.cmd`，自动使用 `py -3` 或 PATH 中的 `python` | 双击 `Launch.cmd` |
| macOS | 打开 `Setup.command` | 打开 `Launch.command` |

Setup 在代码目录建立 `.venv`，安装 requirements，并使用 `constraints-handoff.txt` 固定本轮测试的直接依赖版本。
间接依赖仍由 pip 解析，这不是完整跨平台锁文件。不要从另一台电脑复制 `.venv`。
Launch 不安装依赖、不拉 Git 更新、不升级代码。可以为 Launch 创建桌面快捷方式。
这不是签名的原生安装包。使用期间保留启动窗口，Ctrl+C 停止程序；电脑关机/休眠会停止服务。

Mac 如果没有执行权限，在项目目录运行 `chmod +x Setup.command Launch.command`。
也可手动运行：

```bash
python3 helpers/setup_local.py
.venv/bin/python helpers/launch_local.py
```

Windows 启动命令为 `.venv\Scripts\python.exe helpers\launch_local.py`。
默认只监听 `http://127.0.0.1:8501`；端口被占用会报错而不是连接未知服务。
可用 `--port 8502` 换端口；`--no-browser` 可关闭自动打开浏览器。

## 授权与数据位置

首页上传 Google **Desktop app** OAuth JSON，点击 **Connect Gmail**，由实际使用者选择自己的 Google 邮箱授权。
不要复制开发者的 token。凭证获取方法见 [Gmail 教程](gmail_setup.md)。
当前后端是 Gmail / Google Workspace；Outlook 选信入口不等于支持 Microsoft 365 / Exchange 邮箱。

Launch 的默认数据位置独立于代码目录：

| 系统 | 数据目录 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Eml\` |
| macOS | `~/Library/Application Support/Eml/` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/eml/` |

`auth/` 保存 credentials 和 token；`client_profiles.sqlite3` 保存客户、背景文档、草稿、待处理包及本地还原映射。
不同电脑不会自动同步。本版没有多人共享权限，也没有自行实现数据库加密。
映射包含真实资料，应使用受控的本机账号、磁盘加密和私有备份。POSIX 文件权限保护不等同于 Windows ACL 验证。

`--data-dir` 或 `EML_DATA_DIR` 可改数据根目录。显式 `EML_AUTH_DIR` / `EML_PROFILE_DB` 仍优先。
直接运行旧的 `streamlit run client_workspace.py` 使用项目目录的数据默认值，不是 Launch 的新位置。
如果旧资料在当前 checkout，先停止旧程序并备份，再运行：

```bash
.venv/bin/python helpers/launch_local.py --migrate-from-project
```

Windows 将解释器换为 `.venv\Scripts\python.exe`。迁移只复制当前 checkout 根目录的 credentials/token 和
`data/client_profiles.sqlite3`，用 SQLite backup API 复制数据库；目标已有文件时拒绝覆盖，不删除旧资料。
旧资料在其它路径时应显式指定原路径或从备份恢复，不能假设不同 checkout 使用同一份资料。

公司应持有 Google 项目配置。External + Testing 的 OAuth 项目使用 Gmail 范围时，refresh token 通常七天失效。
同一 Workspace 组织内可由管理员核对 Internal 等适用配置；公开 Production 的验证要求需另行处理。
[Google OAuth 说明](https://developers.google.com/identity/protocols/oauth2)

## 无需本地模型的日常流程

1. Connect Gmail，新建/选择客户，在 **Client & scope** 选择日期与邮件来源。
2. 在 **Review emails** 筛选邮件，检查回复和附件抽取结果，然后 **Use selected emails →**。
3. 在 **Draft & export → Writing preferences** 修改 **Output preferences** 和额外替换规则，保存设置。
   新客户 **Keep this client's processing local** 默认不勾选；旧客户保留原设置。勾选后阻止云包准备与发送。
4. 在 **Draft inputs** 选择必要背景文档，点击 **Prepare prompt + emails for GPT**。
   准备在本地执行，不发送网络请求。默认界面没有本地模型或生成方式切换。
5. 在 **Pending cloud packages** 展开 **Inspect the complete outgoing request**，核对脱敏后的正文、附件和业务背景。
   需要调整时修改范围/替换规则并生成新包；旧包是快照，不随输入变化自动更新。
6. 确认允许云使用后，勾选审阅确认，采用以下任一路径。

**手动复制，不需要 API key：** 点击 **Copy prompt + emails for GPT**，粘贴到获准的模型服务。
剪贴板不可用时用 **Download prompt + emails** 下载 `gpt_prompt.txt`。
也可下载结构化的 `eml_cloud_request.json`。要求模型返回符合 `response_schema` 的纯 JSON，
保留包 ID、证据摘要和原文引用。通过 **Upload cloud response JSON to restore locally** 上传，
点击 **Restore and save response**。不要把数据库或原始恢复映射交给模型。

**可选 Gemini API：** 展开 **Or generate with Gemini API**，填写项目可用的 **Gemini model ID** 与 **Gemini API key**，
确认项目有效 Cloud Billing 与使用许可后点击 **Send reviewed package to Gemini**。
只发送当前已审阅的包，不自动重试。API key 仅存当前会话，也可使用本机 `GEMINI_API_KEY` / `GEMINI_MODEL` 环境变量。
`.env` 不自动加载。OAuth JSON 与 Gemini API key 是不同凭证。
界面中的 billing 确认是人工声明，程序不查询账单状态，也不保证免费；安装检查不发真实计费请求。

恢复后的活动需逐条核对来源、工作状态与措辞，再保存审核记录并导出 Word。
重启后连接同一 Gmail、选择同一客户，可从 **Saved drafts** 或待处理包继续；不必重新扫描邮箱。
目前界面仍需 Gmail 连接入口，不是独立离线查看器。删除待处理包前确认不再需要其恢复映射。

本地模型备选保存在 `optional/local-llm` 分支。主线保留兼容代码，维护者可显式设置 `EML_ENABLE_LOCAL_LLM=1` 启用原入口，
见[本机模型教程](ollama_setup.md)。普通启动不需要该变量，背景文档仍可本地抽取并人工确认。
云生成只包含 Draft inputs 选定的背景文档；不会自动发送全部文件。

## 检查与故障排查

Windows：

```powershell
.venv\Scripts\python.exe helpers\launch_local.py --check
```

Mac：`.venv/bin/python helpers/launch_local.py --check`。
自定义启动目录/端口时带上相同的 `--data-dir` / `--port`。
该入口将 Launch 实际使用的授权目录、数据库和端口传给诊断工具，不启动登录或读取邮件。
诊断检查依赖、DNS、验证证书的 Google HTTPS、OAuth 文件元数据、SQLite 只读完整性与本地服务健康，不显示 secret/token。
底层 `helpers/check_runtime.py` 另支持 `--offline`、`--auth-dir`、`--database`；直接调用时须传正确路径。

没有错误时退出 0；新安装缺凭证或未启动服务可能只显示 warning，需要人工判断。
服务健康不代表 Gmail 已授权，保存 refresh token 也不保证 token 没有失效。
授权超时后重新点击连接；External Testing 到期可重新授权，不需要删除客户数据库。
不要用关闭证书校验或固定 Google IP 的方式处理网络问题。

## 备份、恢复与升级

停止程序后备份整个数据目录，或运行以下命令。目标文件夹需已存在，ZIP 文件名不得重复：

```powershell
.venv\Scripts\python.exe helpers\backup_local.py --output "C:\EmlBackups\eml-2026-11-17.zip"
```

Mac：`.venv/bin/python helpers/backup_local.py --output "$HOME/EmlBackups/eml-2026-11-17.zip"`。
自定义 `--data-dir` 时也给备份命令传同一路径；显式 `EML_AUTH_DIR` / `EML_PROFILE_DB` 仍优先。
备份包含 SQLite 一致性快照、授权文件和映射，不包含代码或虚拟环境，没有 ZIP 加密。存放在公司控制的私有备份位置。

恢复时停止 Eml，把自己生成的 ZIP 解压到一个新的私有目录，用 `--data-dir` 指向它启动，验证客户、草稿和待处理包。
若用环境变量覆盖路径，恢复时也须同步调整，避免仍访问原目录。确认恢复有效前保留原资料。
只有下载的云请求无法重建原信息；必须保留数据库中的映射。

交接时记录 Git 提交号。升级前备份、停止程序，再更换代码并按需执行 Setup。
不要让两个 checkout 同时写同一数据库。日常 Launch 不更新版本。
默认写作偏好在 `prompts/billing_style.md`，已保存的客户偏好在数据库，Word 布局由 `invoice/renderer.py` 控制。
程序不自动推算工时/费用，也不发出 invoice。

开发验证：`python -m unittest discover -s tests -q`，使用合成资料与模拟接口，不发送真实客户邮件。
