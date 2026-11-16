"""Build a clean Windows handoff ZIP from the committed trial branch."""
import argparse
import io
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "Eml-Windows/"
ENTRYPOINTS = {
    "Install.cmd": "Setup.cmd",
    "Start.cmd": "Launch-Windows-Test.cmd",
    "Try-Demo.cmd": "Try-Demo.cmd",
}
README = """Eml Windows 测试版

1. 全部解压这个文件夹，不要在 ZIP 预览里运行。
2. 首次安装：电脑需要 Python 3.11+，双击 Install.cmd，联网安装依赖。
3. 日常使用：双击 Start.cmd，在浏览器中操作；保留终端窗口。
4. 不用登录的演示：双击 Try-Demo.cmd，使用虚构客户与邮件。

Start.cmd 就是软件入口；Install.cmd 只在首次安装或更新依赖时使用。
退出时在启动窗口按 Ctrl+C。无需运行任何 .py 文件。

第一次用自己的 Gmail：页面内选择“创建自己的凭证”，按六步创建项目、下载 JSON，然后上传并授权。
所有内部文件放在 _app，日常不用打开它。
完整说明：_app/START-HERE-WINDOWS.md
诊断：_app/Check-Windows-Test.cmd
备份：关闭应用后运行 _app/Backup-Windows-Test.cmd

测试数据：%LOCALAPPDATA%\\Eml-Windows-Test
程序文件夹和数据目录独立；删除程序文件夹不会自动清除邮箱授权或测试资料。
"""


def package_source(source_zip, output):
    """Nest tracked source under _app and refuse accidental private/runtime files."""
    with zipfile.ZipFile(io.BytesIO(source_zip)) as source:
        files = [item for item in source.infolist() if not item.is_dir()]
        names = {item.filename for item in files}
        required = {*ENTRYPOINTS.values(), "helpers/windows_trial.py", "eml_ui/client_workspace.py"}
        if not required <= names:
            raise ValueError("Build from the Windows trial branch with the reorganized source tree.")
        for item in files:
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or any(part in {".git", ".venv", "data", "__pycache__"} for part in path.parts):
                raise ValueError("Archive contains a runtime/private directory or invalid path.")
            if path.name.lower() in {"credentials.json", "token.json", "clients.json", ".env", "secrets.toml"} or path.suffix in {".sqlite", ".sqlite3"}:
                raise ValueError("Archive contains local credentials or client data.")
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as target, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
            for item in files:
                bundle.writestr(PREFIX + "_app/" + item.filename, source.read(item))
            for name, command in ENTRYPOINTS.items():
                wrapper = f'@echo off\r\nsetlocal\r\ncd /d "%~dp0_app"\r\ncall "{command}"\r\n'
                if name == "Install.cmd":
                    wrapper += "pause\r\n"
                bundle.writestr(PREFIX + name, wrapper.encode("ascii"))
            bundle.writestr(PREFIX + "README.txt", README.encode("utf-8-sig"))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        parser.error("Commit the release changes first; packaging only uses committed source.")
    archive = subprocess.check_output(["git", "archive", "--format=zip", "HEAD"], cwd=ROOT)
    try:
        output = package_source(archive, args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Package ready: {output.resolve()}")


if __name__ == "__main__":
    main()
