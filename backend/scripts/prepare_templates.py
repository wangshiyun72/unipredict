"""准备 4 个数据模板的示例数据。

用法（在 backend 目录下）：
    python scripts/prepare_templates.py                 # 自动生成模拟数据 + 下载公开数据集
    python scripts/prepare_templates.py --esol 路径      # 手动指定已下载的 delaney-processed.csv
    python scripts/prepare_templates.py --tox 路径       # 手动指定已下载的 qsar_fish_toxicity.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from app.services import templates as tpl  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--esol", help="本地 delaney-processed.csv 路径")
    ap.add_argument("--tox", help="本地 qsar_fish_toxicity.csv 路径")
    ap.add_argument("--force", action="store_true", help="重新生成/下载")
    args = ap.parse_args()

    if args.force:
        for k in tpl.TEMPLATES:
            tpl.template_path(k).unlink(missing_ok=True)
    if args.esol:
        tpl._download = lambda url, timeout=30: Path(args.esol).read_bytes()  # type: ignore[assignment]
        tpl._get_esol().to_csv(tpl.template_path("solubility"), index=False, encoding="utf-8-sig")
    if args.tox:
        df = pd.read_csv(args.tox, sep=";", header=None)
        df.columns = ["CIC0", "SM1_Dz", "GATS1i", "NdsCH", "NdssC", "MLOGP", "LC50"]
        df.to_csv(tpl.template_path("aquatic_toxicity"), index=False, encoding="utf-8-sig")

    for key, status in tpl.prepare_all().items():
        info = tpl.template_status(key)
        print(f"{tpl.TEMPLATES[key]['name']:<16} {status:<6} {info.get('n_rows', '-')} 行")


if __name__ == "__main__":
    main()
