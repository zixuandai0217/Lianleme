@echo off
chcp 65001 >nul
cd /d R:\Lianleme
R:\Lianleme\backend\.venv\Scripts\python.exe tools\quality_gate.py --full > R:\Lianleme\.scratch\gate.log 2>&1
echo EXIT=%ERRORLEVEL%>> R:\Lianleme\.scratch\gate.log
