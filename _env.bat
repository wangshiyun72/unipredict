@echo off
REM ===== 定位 unipredict conda 环境（被其他脚本调用，不需要单独运行）=====
REM 双击 .bat 时 cmd 里通常没有 conda 命令，这里直接从 conda 的环境登记文件里找到环境路径
set "UP_ENV="
if exist "%USERPROFILE%\.conda\environments.txt" (
  for /f "usebackq delims=" %%i in ("%USERPROFILE%\.conda\environments.txt") do (
    if /i "%%~nxi"=="unipredict" if exist "%%i\python.exe" set "UP_ENV=%%i"
  )
)
if not defined UP_ENV (
  for %%r in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "C:\ProgramData\anaconda3" "C:\ProgramData\miniconda3" "D:\anaconda3" "D:\miniconda3" "D:\Anaconda" "E:\anaconda3") do (
    if exist "%%~r\envs\unipredict\python.exe" set "UP_ENV=%%~r\envs\unipredict"
  )
)
if not defined UP_ENV (
  echo 找不到 conda 环境 unipredict。请先在 Anaconda Prompt 中运行 setup_backend.bat
  exit /b 1
)
REM 模拟 conda activate：把环境的 DLL 目录加入 PATH（torch / rdkit 等依赖需要）
set "PATH=%UP_ENV%;%UP_ENV%\Library\mingw-w64\bin;%UP_ENV%\Library\usr\bin;%UP_ENV%\Library\bin;%UP_ENV%\Scripts;%PATH%"
set "PY=%UP_ENV%\python.exe"
exit /b 0
