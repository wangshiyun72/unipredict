@echo off
chcp 65001 >nul
REM ===== 前端环境安装（只需运行一次）=====
REM 需要先安装 Node.js 22 LTS：https://npmmirror.com/mirrors/node/ 下载 node-v22.x-x64.msi
cd /d %~dp0
where node >nul 2>nul
if errorlevel 1 (
  echo 未检测到 Node.js，请先安装 Node.js 22 LTS（见 docs\部署说明.md 第 1 步）
  pause
  exit /b 1
)
node -v
call npm config set registry https://registry.npmmirror.com
cd frontend
call npm install
echo.
echo 前端依赖安装完成。启动：先运行 start_backend.bat，再运行 start_frontend.bat
pause
