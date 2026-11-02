@echo off
chcp 65001 >nul
cd /d R:\Lianleme\web
npx vitest run > R:\Lianleme\.scratch\web-tests.log 2>&1
echo EXIT=%ERRORLEVEL%>> R:\Lianleme\.scratch\web-tests.log
