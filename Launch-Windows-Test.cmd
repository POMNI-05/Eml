@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup.cmd once, then open Launch-Windows-Test.cmd again.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" helpers\windows_trial.py launch
if errorlevel 1 pause
