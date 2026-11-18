"""环境检查：python scripts/check_env.py"""
import importlib
import platform
import shutil
import subprocess
import sys

print(f"Python {sys.version.split()[0]}  ({platform.system()} {platform.machine()})")
if sys.version_info < (3, 10):
    print("  !! 需要 Python 3.10 或以上（推荐 3.11）")

groups = {
    "核心依赖（必需）": ["fastapi", "uvicorn", "multipart", "pydantic", "jwt", "numpy", "pandas", "sklearn",
                   "joblib", "openpyxl"],
    "可选依赖": ["torch", "tabpfn", "xgboost", "lightgbm", "rdkit", "onnxruntime", "matplotlib"],
}
for title, mods in groups.items():
    print(f"\n{title}")
    for m in mods:
        try:
            mod = importlib.import_module(m)
            print(f"  [OK] {m:<12} {getattr(mod, '__version__', '')}")
        except Exception as e:
            print(f"  [--] {m:<12} 未安装（{type(e).__name__}）")

try:
    import torch

    print(f"\nPyTorch {torch.__version__}  CUDA 可用：{torch.cuda.is_available()}")
    if torch.cuda.is_available():
        p = torch.cuda.get_device_properties(0)
        print(f"  GPU：{p.name}  显存 {p.total_memory / 1024**3:.1f} GB  算力 sm_{p.major}{p.minor}")
        x = torch.randn(256, 256, device="cuda")
        print(f"  GPU 计算测试通过：{float((x @ x).sum()):.2f}")
    else:
        print("  !! 当前 torch 不支持 CUDA。RTX 50 系显卡需要 CUDA 12.8 版本的 torch（见 docs/部署说明.md）")
except Exception as e:
    print(f"\nPyTorch 检查失败：{e}")

node = shutil.which("node")
if node:
    v = subprocess.run([node, "-v"], capture_output=True, text=True).stdout.strip()
    print(f"\nNode.js {v}")
else:
    print("\n[--] 未检测到 Node.js（前端开发/构建需要，见 docs/部署说明.md）")
