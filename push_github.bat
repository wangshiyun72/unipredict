@echo off
chcp 65001 >nul
REM ===== 构建前端并推送到 GitHub（wangshiyun72/unipredict）=====
REM 第一次运行前：先在 https://github.com/new 创建一个名为 unipredict 的 Public 空仓库（不要勾选 README）
cd /d %~dp0
set "REPO=https://github.com/wangshiyun72/unipredict.git"

echo [1/3] 构建前端（生成 frontend\dist，服务器部署时直接使用）...
cd frontend
call npm run build
if errorlevel 1 (
  echo 前端构建失败，请把报错截图发给 Claude
  pause
  exit /b 1
)
cd ..

echo [2/3] 提交代码...
if not exist .git (
  git init
  git branch -M main
)
git config user.name >nul 2>nul || git config user.name "wangshiyun72"
git config user.email >nul 2>nul || git config user.email "wangshiyun72@users.noreply.github.com"
git remote get-url origin >nul 2>nul || git remote add origin %REPO%
git add -A
git status --short
git commit -m "UniPredict: 基于服务器端通用模型的可访问式深度学习预测服务" >nul 2>nul
git branch -M main

echo [3/3] 推送到 GitHub...
echo 国内直连 GitHub 经常超时。如果你开着代理软件，请输入它的本地端口：
echo   Clash for Windows 一般是 7890，Clash Verge 是 7897，v2rayN 是 10808
set "PROXY_PORT="
set /p PROXY_PORT=代理端口（没有代理直接回车）：
if defined PROXY_PORT (
  git -c http.proxy=http://127.0.0.1:%PROXY_PORT% -c https.proxy=http://127.0.0.1:%PROXY_PORT% push -u origin main
) else (
  git push -u origin main
)
if errorlevel 1 (
  echo.
  echo 推送失败。常见原因：1）GitHub 上还没有创建 unipredict 仓库；2）网络问题，可以开代理后重试。
  pause
  exit /b 1
)
echo.
echo 完成：https://github.com/wangshiyun72/unipredict
pause
