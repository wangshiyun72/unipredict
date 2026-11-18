#!/usr/bin/env bash
# =============================================================================
#  通用模型预测服务平台 —— 云服务器一键部署脚本（Ubuntu 22.04 / 24.04，CPU 服务器）
#
#  用法（以 root 身份在服务器上执行）：
#     git clone https://github.com/wangshiyun72/unipredict.git /opt/unipredict
#     bash /opt/unipredict/deploy/install.sh
#
#  完成后浏览器访问 http://服务器公网IP/   （需在安全组中放行 80 端口）
#  重复运行本脚本 = 更新代码依赖并重启服务（数据库和模型不会丢失）
# =============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$APP_DIR/venv"
PORT="${PORT:-80}"
PIP_INDEX="${PIP_INDEX:-https://mirrors.aliyun.com/pypi/simple/}"

green() { echo -e "\033[32m$*\033[0m"; }
red() { echo -e "\033[31m$*\033[0m"; }

if [ "$(id -u)" -ne 0 ]; then red "请用 root 用户运行（或在命令前加 sudo）"; exit 1; fi
cd "$APP_DIR"
green "[1/7] 项目目录：$APP_DIR"

# ---------- 系统依赖 ----------
green "[2/7] 安装系统依赖（python3 / venv / git）..."
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip git curl libgomp1
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y python3.11 python3.11-pip git curl libgomp || dnf install -y python3 python3-pip git curl
else
  red "不支持的系统，请使用 Ubuntu 22.04 / 24.04 镜像"; exit 1
fi
PY_SYS="$(command -v python3.11 || command -v python3)"
"$PY_SYS" - <<'EOF'
import sys
assert sys.version_info >= (3, 10), f"需要 Python 3.10+，当前 {sys.version}"
EOF

# ---------- Python 虚拟环境 ----------
green "[3/7] 创建 Python 虚拟环境并安装依赖（国内镜像，约 5~10 分钟）..."
[ -d "$VENV" ] || "$PY_SYS" -m venv "$VENV"
PIP="$VENV/bin/pip"
"$PIP" install -U pip -i "$PIP_INDEX"
# CPU 版 PyTorch（服务器没有显卡；官方 PyPI 上 Linux 默认是 CUDA 版，体积 2GB+，这里显式装 CPU 版）
if ! "$VENV/bin/python" -c "import torch" 2>/dev/null; then
  "$PIP" install filelock typing-extensions sympy networkx jinja2 fsspec setuptools -i "$PIP_INDEX"
  "$PIP" install --no-deps --no-index -f https://mirrors.aliyun.com/pytorch-wheels/cpu/ torch \
    || "$PIP" install torch --index-url https://download.pytorch.org/whl/cpu
fi
"$VENV/bin/python" -c "import torch; print('torch', torch.__version__)"
"$PIP" install -r backend/requirements.txt -i "$PIP_INDEX"
"$PIP" install -r backend/requirements-optional.txt -i "$PIP_INDEX" || red "部分可选依赖安装失败（不影响运行，对应模型会显示未安装）"

# ---------- 配置 ----------
green "[4/7] 生成配置 backend/.env ..."
ENV_FILE="$APP_DIR/backend/.env"
if [ ! -f "$ENV_FILE" ]; then
  ADMIN_PWD="${ADMIN_PASSWORD:-$(head -c 12 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 12)}"
  cat > "$ENV_FILE" <<EOF
# 云服务器（CPU）配置，修改后执行 systemctl restart unipredict 生效
PORT=$PORT
DEVICE=cpu
DEFAULT_ADMIN_USER=admin
DEFAULT_ADMIN_PASSWORD=$ADMIN_PWD
ALLOW_REGISTER=true
TRAIN_WORKERS=1
MAX_JOBS_PER_USER=1
PREDICT_CONCURRENCY=4
GPU_CONCURRENCY=1
TABPFN_MAX_TRAIN_ROWS=1000
RATE_LIMIT_USER_PER_MIN=300
RATE_LIMIT_KEY_PER_MIN=60
MAX_UPLOAD_MB=20
HF_ENDPOINT=https://hf-mirror.com
EOF
  chmod 600 "$ENV_FILE"
  echo "$ADMIN_PWD" > "$APP_DIR/backend/.admin_password_initial"
  chmod 600 "$APP_DIR/backend/.admin_password_initial"
fi

# ---------- 准备数据与演示模型 ----------
green "[5/7] 准备数据模板，训练并公开演示模型（CPU 上约 5~15 分钟，只在首次执行）..."
cd "$APP_DIR/backend"
"$VENV/bin/python" scripts/prepare_templates.py
"$VENV/bin/python" scripts/seed_demo.py --fast || red "演示模型初始化未完成，可稍后在网页「数据模板」中手动一键训练"
cd "$APP_DIR"

# ---------- systemd 服务 ----------
green "[6/7] 注册系统服务（开机自启、崩溃自动重启）..."
cat > /etc/systemd/system/unipredict.service <<EOF
[Unit]
Description=UniPredict 通用模型预测服务平台
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR/backend
ExecStart=$VENV/bin/python -m app.main
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable unipredict >/dev/null 2>&1
systemctl restart unipredict

# 系统防火墙（云厂商的安全组仍需在控制台放行）
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then ufw allow "$PORT"/tcp || true; fi

# ---------- 检查 ----------
green "[7/7] 等待服务启动..."
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
if curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1; then
  IP="$(curl -fsS --max-time 5 http://100.100.100.200/latest/meta-data/eipv4 2>/dev/null || curl -fsS --max-time 5 https://ifconfig.me 2>/dev/null || echo 服务器公网IP)"
  green "=================================================="
  green " 部署完成！"
  green " 网页地址：  http://$IP$( [ "$PORT" = 80 ] || echo ":$PORT" )/"
  green " 接口文档：  http://$IP$( [ "$PORT" = 80 ] || echo ":$PORT" )/docs"
  if [ -f "$APP_DIR/backend/.admin_password_initial" ]; then
    green " 管理员：    admin / $(cat "$APP_DIR/backend/.admin_password_initial")（请登录后修改）"
  fi
  green " 查看日志：  journalctl -u unipredict -f"
  green " 更新代码：  cd $APP_DIR && git pull && bash deploy/install.sh"
  green "=================================================="
  green " 如果浏览器打不开：到云服务器控制台 → 安全组 → 入方向放行 TCP $PORT 端口"
else
  red "服务没有正常启动，查看日志：journalctl -u unipredict -n 100 --no-pager"
  exit 1
fi
