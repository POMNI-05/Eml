# 从哪里启动，文件放在哪里

## 日常入口

| 使用方式 | 首次安装 | 每次打开 |
| --- | --- | --- |
| 项目文件夹里的 Windows 版 | `Setup.cmd` | **`Launch.cmd`** |
| 项目文件夹里的 Mac 版 | `Setup.command` | **`Launch.command`** |
| 整理后的 Windows 交付包 | `Install.cmd` | **`Start.cmd`** |

软件打开后在浏览器使用；启动文件负责启动本机服务并打开浏览器，不是要求你运行某个 Python 源文件。
使用期间保留终端窗口，关闭时按 Ctrl+C。Windows 交付包另有 `Try-Demo.cmd`，只用合成数据演示。

## 源码目录

| 位置 | 用途 |
| --- | --- |
| `eml_ui/` | 当前 Streamlit 界面、Gmail 设置引导、云包与审核面板 |
| `eml_core/` | Gmail、客户资料、附件、Outlook 选信等共用功能 |
| `eml_core/outlook_scripts/` | Mac Outlook AppleScript 适配 |
| `invoice/` | 工作记录、证据校验、脱敏交换与 Word 导出 |
| `helpers/` | 安装、启动、备份、诊断、演示和打包工具 |
| `legacy/` | 旧界面及早期手动实验入口；不用于日常启动 |
| `examples/` | 可复制的合成示例配置 |
| `assets/`、`prompts/` | 界面样式和写作指令 |
| `docs/` | 使用说明、架构、开发笔记和截图 |
| `tests/` | 自动化测试 |
| `data/` | 本机工作目录，不提交 Git；含测试工作树、验证输出和打包文件 |

启动器实际运行 `eml_ui/client_workspace.py`。文件移动后，导入、脚本位置、测试和文档引用一并更新。
从项目根目录开发调试可运行 `python -m streamlit run eml_ui/client_workspace.py`；日常仍使用 Launch，
这样授权和数据库路径与安装说明一致。旧 `app.py` 已归入 `legacy/`。

## 交付包

Windows 交付包外层仅保留 `Install.cmd`、`Start.cmd`、`Try-Demo.cmd`、`README.txt` 和 `_app/`。
所有程序内部文件与维护工具都在 `_app/`；无需进入它来日常使用。
压缩包不携带 `.venv`、用户授权或数据库，安装后虚拟环境在 `_app/.venv` 内创建。

目录整理不迁移用户资料：主线仍使用系统 Eml 数据目录；Windows 隔离版仍使用
`%LOCALAPPDATA%\Eml-Windows-Test`。旧测试压缩包保留版本号，避免覆盖你已经拿去测试的包。
