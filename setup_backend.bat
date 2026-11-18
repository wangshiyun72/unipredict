@echo off
chcp 65001 >nul
REM ===== 后端环境安装（只需运行一次）=====
REM 需要先安装 Anaconda/Miniconda；如果提示找不到 conda，请在“Anaconda Prompt”里进入本目录再运行此脚本
cd /d %~dp0
echo [1/5] 创建 conda 环境 unipredict（Python 3.11）...
REM 用清华 conda-forge 镜像建环境（--override-channels 不走 Anaconda 默认频道，无需接受其服务条款，国内也更快）
call conda env list | findstr /C:"unipredict" >nul
if not errorlevel 1 goto activate
call conda create -n unipredict python=3.11 -y --override-channels -c https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge
if errorlevel 1 call conda create -n unipredict python=3.11 -y --override-channels -c conda-forge
:activate
call conda activate unipredict
if errorlevel 1 (
  echo 激活 conda 环境失败，请在 Anaconda Prompt 中运行本脚本
  pause
  exit /b 1
)
echo [2/5] 设置 pip 国内镜像（清华源）...
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
echo [3/5] 安装核心依赖...
pip install -r backend\requirements.txt
echo [4/5] 安装 CUDA 12.8 版 PyTorch（RTX 50 系显卡必须用 cu128）...
pip install torch --index-url https://download.pytorch.org/whl/cu128
echo [5/5] 安装可选依赖（TabPFN / XGBoost / LightGBM / RDKit / ONNX Runtime）...
pip install -r backend\requirements-optional.txt
echo.
echo ===== 环境检查 =====
cd backend
python scripts\check_env.py
echo.
echo ===== 准备数据模板 =====
python scripts\prepare_templates.py
echo.
echo 后端环境安装完成。下一步运行 setup_frontend.bat
pause
