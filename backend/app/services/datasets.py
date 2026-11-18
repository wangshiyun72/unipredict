"""数据集管理：保存上传文件、生成数据画像、读取数据。"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from .. import db
from ..config import settings
from ..core.preprocess import profile_dataframe, read_table

ALLOWED_EXT = (".csv", ".xlsx", ".xls", ".txt")


def save_dataset(owner_id: int, filename: str, content: bytes, name: str | None = None,
                 template_key: str | None = None, description: str | None = None,
                 visibility: str = "private") -> dict[str, Any]:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"不支持的文件类型 {ext}，请上传 CSV 或 Excel 文件")
    if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"文件超过 {settings.MAX_UPLOAD_MB} MB 上限")
    path = Path(settings.DATASET_DIR) / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(content)
    try:
        df = read_table(str(path))
    except Exception as e:
        path.unlink(missing_ok=True)
        raise ValueError(f"文件读取失败：{e}") from e
    if df.empty or df.shape[1] < 2:
        path.unlink(missing_ok=True)
        raise ValueError("数据至少需要 2 列（特征 + 目标）且不能为空")
    # 统一存成 UTF-8 CSV，后续读取更快更稳
    csv_path = path.with_suffix(".csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    if csv_path != path:
        path.unlink(missing_ok=True)
    profile = profile_dataframe(df)
    ds_id = db.insert(
        "datasets",
        {
            "owner_id": owner_id,
            "name": name or Path(filename).stem,
            "filename": filename,
            "path": str(csv_path),
            "n_rows": int(len(df)),
            "n_cols": int(df.shape[1]),
            "profile_json": profile,
            "template_key": template_key,
            "description": description,
            "visibility": visibility,
            "created_at": db.now(),
        },
    )
    return db.query_one("SELECT * FROM datasets WHERE id=?", [ds_id])  # type: ignore[return-value]


def load_dataframe(ds: dict[str, Any]) -> pd.DataFrame:
    return read_table(ds["path"])


def preview(ds: dict[str, Any], n: int = 20) -> list[dict[str, Any]]:
    df = load_dataframe(ds).head(n)
    return df.astype(object).where(df.notna(), None).to_dict(orient="records")
