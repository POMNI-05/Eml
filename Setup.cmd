@echo off
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 helpers\setup_local.py
) else (
  python helpers\setup_local.py
)
if errorlevel 1 pause
