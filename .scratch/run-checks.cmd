@echo off
chcp 65001 >nul
if exist R:\Lianleme\.scratch\all-done.txt del R:\Lianleme\.scratch\all-done.txt
cd /d R:\Lianleme\backend
R:\Lianleme\backend\.venv\Scripts\python.exe -m ruff check app tests > R:\Lianleme\.scratch\lint.log 2>&1
echo RUFF=%ERRORLEVEL%>> R:\Lianleme\.scratch\lint.log
cd /d R:\Lianleme\web
call npx tsc -b --force > R:\Lianleme\.scratch\tsc.log 2>&1
echo TSC=%ERRORLEVEL%>> R:\Lianleme\.scratch\tsc.log
call npx eslint src > R:\Lianleme\.scratch\eslint.log 2>&1
echo ESLINT=%ERRORLEVEL%>> R:\Lianleme\.scratch\eslint.log
call npm run build > R:\Lianleme\.scratch\build.log 2>&1
echo BUILD=%ERRORLEVEL%>> R:\Lianleme\.scratch\build.log
cd /d R:\Lianleme\backend
uv run pytest -q > R:\Lianleme\.scratch\backend-tests.log 2>&1
echo PYTEST=%ERRORLEVEL%>> R:\Lianleme\.scratch\backend-tests.log
cd /d R:\Lianleme\web
call npx vitest run > R:\Lianleme\.scratch\web-tests.log 2>&1
echo VITEST=%ERRORLEVEL%>> R:\Lianleme\.scratch\web-tests.log
echo ALLDONE > R:\Lianleme\.scratch\all-done.txt
