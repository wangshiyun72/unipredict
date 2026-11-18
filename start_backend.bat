@echo off
chcp 65001 >nul
REM ===== 启动后端预测服务（端口 8000）=====
call "%~dp0_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
cd /d %~dp0backend
echo 使用 Python：%PY%
echo 接口文档：http://localhost:8000/docs
echo 关闭此窗口即停止服务
"%PY%" -m app.main
pause
