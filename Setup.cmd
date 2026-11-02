@echo off
cd /d "%~dp0"
py -3 helpers\setup_local.py
if errorlevel 1 pause
