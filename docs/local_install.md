# 本机安装、云端生成与交接

适用分支：`codex/local-cloud-billing`。源码从 GitHub 获取，程序在使用者的电脑运行。
开发者电脑关机不影响老板本机的程序。老板自己的电脑休眠或关机后，本机程序仍会停止。
不同员工安装后各自有数据与授权；本版没有跨电脑同步或多人共享权限。

## 首次安装与日常入口

先安装 Python 3.11 或以上版本。取得此分支后，在项目文件夹：

| 系统 | 首次安装 | 以后每次使用 |
| --- | --- | --- |
| macOS | 打开 `Setup.command` | 打开 `Launch.command` |
| Windows | 打开 `Setup.cmd`，需要 Python Launcher 的 `py` 命令 | 打开 `Launch.cmd` |

Setup 会在当前代码目录建立 `.venv` 并安装 requirements。Launch 不安装依赖、
不拉取 Git 更新、不升级代码。可以为 Launch 文件创建桌面替身/快捷方式。
这是启动脚本与本地网页入口，不是已签名的原生 `.app`/`.exe` 安装包。
终端窗口需要在使用期间保持打开，Ctrl+C 可以停止程序。

Mac 若文件没有执行权限，在项目目录执行 `chmod +x Setup.command Launch.command`。
也可以直接在终端运行：

```bash
python3 helpers/setup_local.py
.venv/bin/python helpers/launch_local.py
```

Windows 对应 `.venv\Scripts\python.exe helpers\launch_local.py`。
默认只监听 `http://127.0.0.1:8501`；已有程序占用端口时会停止并提示，
不会悄悄连接一个未知的本地服务。需要时用 `--port 8502`。

## 授权、持久数据与已有资料

通过 Launch 启动时，默认数据位置独立于代码目录：

| 系统 | 目录 |
| --- | --- |
| macOS | `~/Library/Application Support/Eml/` |
| Windows | `%LOCALAPPDATA%\Eml\` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/eml/` |

目录中 `auth/` 保存 Google Desktop credentials 和 token，`client_profiles.sqlite3`
保存客户、文档、搜索设置、草稿、生成偏好、待处理请求与本地复原映射。
映射包含真实信息，应按客户资料保护。POSIX 启动时限制目录/新文件权限；
本版没有自行实现数据库加密，目标电脑应使用适当的账户权限、磁盘加密及受控备份。

`--data-dir /path/to/private/data` 或环境变量 `EML_DATA_DIR` 可改数据根目录。
已有 `EML_AUTH_DIR`、`EML_PROFILE_DB` 显式设置仍优先。直接使用旧的
`streamlit run client_workspace.py` 时，原项目目录默认路径保持不变。

如果旧版已在这个项目目录里使用过：先停止旧程序，再备份；需要复制到新目录时运行：

```bash
.venv/bin/python helpers/launch_local.py --migrate-from-project
```

这只复制当前 checkout 根目录的 credentials/token 和 `data/client_profiles.sqlite3`，
用 SQLite backup 复制数据库；目的地已有对应文件时拒绝覆盖。不会删除旧文件。
若旧数据在另一个 checkout 或已有自定义路径，请指定原来的环境变量继续使用，
或在程序关闭后从已确认的备份迁移，不能假定两个 checkout 的数据相同。

新安装在首页上传 Google Desktop OAuth JSON、点击 Connect Gmail。
获取方式见 [Gmail 教程](gmail_setup.md)。公司项目、登录邮箱和授权由公司管理更适合长期交接。
External + Testing 的 OAuth refresh token 通常七天失效；这不表示客户档案丢失。
Workspace Internal 与公开 Production 的要求不同，不能仅为避免七天限制便盲目改为公开发布。
`gmail.readonly` 属于 restricted scope；是否需要验证/安全评估取决于组织内部等适用例外。

## 无需安装 Ollama 的生成流程

1. Connect Gmail，选择客户/文件夹或搜索范围。
2. 在邮件列表勾选或排除邮件，检查附件抽取，进入 **Draft & export**。
3. 打开 **Client generation preferences**，修改 **Output preferences**，填写额外替换规则。
   默认只允许本地处理；仅在允许云处理的客户上取消 **Keep this client's processing local**，
   点击 **Save generation preferences**。
4. 在 **Draft inputs** 中选择必要的背景文档。确认档案中客户关系与服务范围准确。
5. 将 **Generation method** 设成 **Cloud JSON / Gemini**，点击 **Prepare cloud evidence package**。
   此步骤仅在本机运行，不需要模型，不会发送任何请求。
6. 在 **Pending cloud packages** 展开完整请求预览。检查残留姓名、地址、业务秘密和附件文字；
   如需修改，调整范围/客户档案/替换规则，重新准备一个包。旧包不会随输入变化而改写。
7. 确认该请求允许云使用后，选择以下方式之一。

**手动方式：** 下载 `eml_cloud_request.json`，只将这个请求交给获准的云服务。
要求服务遵守 `system_instruction`、读取 `input`，返回符合 `response_schema` 的 JSON。
包 ID 和证据摘要应原样返回；不要省略 source quote 或擅自修改 token。
将纯 JSON 保存成文件，通过 **Upload cloud response JSON to restore locally** 上传，
点击 **Restore and save response**。不要把“原始证据备份”或整个 SQLite 文件交给模型。

**Gemini API：** 在相同待处理包中展开 **Or generate with Gemini API**，填写项目可用的
**Gemini model ID** 和 **Gemini API key**，确认该项目具有有效 Cloud Billing 并已获准，
点击 **Send reviewed package to Gemini**。代码只发送当前预览对应的请求，不自动重试。
API key 只在当前 App 会话内；也可用本机环境变量 `GEMINI_API_KEY` 和 `GEMINI_MODEL`。
`.env` 不会自动加载。Google Desktop OAuth JSON 和 Gemini API key 是不同凭证。
模型名由界面/环境变量提供，不将某个可能退役的模型固化成默认路由。

Gemini 免费 API 可用于独立的公开/合成开发样本，不能据此推断真实客户邮件适合免费服务。
本 UI 处理真实 Gmail 证据，因此 Gemini 入口要求 billing-enabled 项目的人工声明；
它不自动读取账单状态，不保证调用免费，也没有开通 Billing 或发出真实请求作为安装检查。
即使 Paid 项目仍需由公司核对条款、客户许可和数据处理安排。

恢复后在当前云方式下审核活动，或者通过 **Saved drafts** 打开已保存结果。
完整原文与映射留在本地快照，核对通过后可继续编辑、保存与导出 Word。
重启后先通过现有 Connect Gmail 进入工作区，再选择同一客户即可打开待处理包并导入结果；
无需重新选择邮件或重新扫描邮箱。当前界面仍需要 Gmail 连接入口，不是完全离线的独立查看器。
导入成功不会自动删除映射；不再需要的待处理包可在界面删除。

需要严格本地处理时，保持客户 local-only，沿用 **Local Ollama** 与
[本机模型教程](ollama_setup.md)。自动背景文档语义分析目前仍使用原 Ollama 入口；
选择云生成并不会把所有背景文档自动送云，只有 Draft inputs 选定的文档随该请求送出。

## 模板、备份与升级

默认文字偏好在 `prompts/billing_style.md`；已保存客户的偏好与替换规则在其本地数据库中。
Word 布局继续由 `invoice/renderer.py` 控制。本版没有自动训练模型、自动填工时/价格、
自动发出 invoice 或从最终账单反向学习收费决定。

停止程序后备份整个数据目录，备份应与原数据同等级保护。待处理云包需要数据库中的映射才能
复原；只有下载的云请求无法重建原信息。升级时先记录 Git 提交和备份，明确选取一个版本，
关闭程序后换代码、按需要更新其虚拟环境，再启动。不要让两个 checkout 同时写同一个数据库。
本轮新增表可与旧代码共存；回退代码不移除新表，也不会撤回已发生的云发送。

开发检查：

```bash
python -m unittest discover -s tests -q
```

测试使用模拟邮箱、合成资料和模拟 Gemini 响应，不发送真实客户邮件。
