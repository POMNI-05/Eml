@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup.cmd first.
  pause
  exit /b 1
)
echo Stop the Windows test workspace before backing up.
".venv\Scripts\python.exe" helpers\windows_trial.py backup
pause
