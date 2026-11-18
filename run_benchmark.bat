@echo off
chcp 65001 >nul
REM ===== 并发压测（需先启动后端，并至少训练好一个模型）=====
call "%~dp0_env.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
cd /d %~dp0backend
set /p MID=请输入要压测的模型 ID：
set /p PWD_ADMIN=请输入 admin 的密码（直接回车 = admin123）：
if "%PWD_ADMIN%"=="" set "PWD_ADMIN=admin123"
"%PY%" scripts\benchmark.py --model %MID% --password "%PWD_ADMIN%"
set "PWD_ADMIN="
echo 结果保存在 backend\benchmark_results\
pause
