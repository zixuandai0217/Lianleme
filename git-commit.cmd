@echo off
chcp 65001 >nul
cd /d R:\Lianleme
git add -A > R:\Lianleme\.scratch\git.log 2>&1
git commit -F R:\Lianleme\.scratch\commit-msg.txt >> R:\Lianleme\.scratch\git.log 2>&1
echo GIT_EXIT=%ERRORLEVEL%>> R:\Lianleme\.scratch\git.log
git log --oneline -1 >> R:\Lianleme\.scratch\git.log 2>&1
echo GITDONE > R:\Lianleme\.scratch\git-done.txt
