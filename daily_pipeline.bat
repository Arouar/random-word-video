@echo off
cd /d "%~dp0"

py main.py
if errorlevel 1 exit /b 1

py upload_video.py