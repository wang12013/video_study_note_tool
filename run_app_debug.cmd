@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m video_notes.cli app
pause
