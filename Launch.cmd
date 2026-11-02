@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup.cmd once, then open Launch.cmd again.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" helpers\launch_local.py
if errorlevel 1 pause
