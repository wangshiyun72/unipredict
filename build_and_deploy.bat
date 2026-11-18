@echo off
chcp 65001 >nul
REM ===== 构建前端并以单端口方式部署（网页和 API 都在 8000 端口）=====
cd /d %~dp0frontend
call npm run build
if errorlevel 1 (
  echo 前端构建失败
  pause
  exit /b 1
)
echo.
echo 构建完成。启动后端后访问 http://localhost:8000 （局域网内其他电脑用 http://本机IP:8000）
cd /d %~dp0
call start_backend.bat
