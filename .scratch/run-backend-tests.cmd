@echo off
chcp 65001 >nul
cd /d R:\Lianleme\backend
uv run pytest -q > R:\Lianleme\.scratch\backend-tests.log 2>&1
echo EXIT=%ERRORLEVEL%>> R:\Lianleme\.scratch\backend-tests.log
