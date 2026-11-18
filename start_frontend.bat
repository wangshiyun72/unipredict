@echo off
chcp 65001 >nul
REM ===== 启动前端（开发模式，端口 5173）=====
cd /d %~dp0frontend
echo 浏览器打开：http://localhost:5173
call npm run dev
pause
