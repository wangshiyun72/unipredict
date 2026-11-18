"""初始化演示模型：用 4 个数据模板各训练一组模型，并把每个模板的最优模型发布、设为全平台公开。

适用于新部署的服务器（全新数据库）。可以重复运行：已有公开最优模型的模板会自动跳过。

用法（在 backend 目录下，后端可以不启动）：
    python scripts/seed_demo.py
    python scripts/seed_demo.py --fast        # 只用轻量模型（无 GPU 的服务器推荐）
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.core.adapters import get_adapter, load_plugins  # noqa: E402
from app.routers.data import _template_dataset  # noqa: E402
from app.security import ensure_default_admin  # noqa: E402
from app.services import templates as tpl  # noqa: E402
from app.services.training import submit_training  # noqa: E402

FAST_MODELS = ["tabpfn", "hist_gb", "random_forest", "linear"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="不训练深度学习模型（CPU 服务器推荐）")
    args = ap.parse_args()

    db.init_db()
    ensure_default_admin()
    load_plugins()
    admin = db.query_one("SELECT * FROM users WHERE role = 'admin' ORDER BY id LIMIT 1")
    assert admin

    for key, t in tpl.TEMPLATES.items():
        exists = db.query_one(
            "SELECT m.id FROM models m JOIN datasets d ON d.id = m.dataset_id "
            "WHERE d.template_key = ? AND m.is_best = 1 AND m.status = 'published' AND m.visibility = 'public'",
            [key],
        )
        if exists:
            print(f"[跳过] {t['name']}：已有公开模型 #{exists['id']}")
            continue
        try:
            ds = _template_dataset(admin, key)
        except Exception as e:
            print(f"[失败] {t['name']}：示例数据准备失败（{e}）")
            continue
        wanted = FAST_MODELS if args.fast else t["recommended_models"] + ["resmlp"]
        models = [m for m in dict.fromkeys(wanted) if get_adapter(m).availability()[0]]
        print(f"[训练] {t['name']}：{models}")
        job_id = submit_training(admin, ds, t["target"], models, task=t["task"],
                                 drop_columns=t.get("drop_for_training"), name_prefix=t["name"])
        while True:
            job = db.query_one("SELECT status, progress, message, result_json FROM jobs WHERE id = ?", [job_id])
            if job and job["status"] in ("succeeded", "failed", "cancelled"):
                break
            time.sleep(2)
        if job["status"] != "succeeded":
            print(f"  失败：{job['message']}")
            continue
        best = job["result"]["best_model_id"]
        db.update("models", best, {"status": "published", "visibility": "public"})
        for r in job["result"]["leaderboard"]:
            m = r.get("metrics") or {}
            flag = "★" if r.get("model_id") == best else " "
            print(f"  {flag} {r['name']:<24} {m.get('primary_label', '')} = {m.get('primary_value', r.get('error'))}")
        print(f"  已发布并公开最优模型 #{best}")

    from app.tasks import task_manager

    task_manager.pool.shutdown(wait=True)
    print("完成。")


if __name__ == "__main__":
    main()
