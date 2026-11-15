@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup.cmd once, then open Try-Demo.cmd again.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" helpers\windows_trial.py demo
if errorlevel 1 pause
