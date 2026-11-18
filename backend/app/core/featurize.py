"""分子结构特征化：把 SMILES 字符串转换成 RDKit 分子描述符。

化工/环境类数据经常以 SMILES 表示分子结构，模型无法直接使用字符串，
这里在预处理之前自动把 SMILES 列展开成一组数值描述符。
RDKit 为可选依赖：未安装时，含 SMILES 的数据会给出明确提示。
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

DESCRIPTOR_NAMES = [
    "MolWt",
    "MolLogP",
    "TPSA",
    "NumHDonors",
    "NumHAcceptors",
    "NumRotatableBonds",
    "RingCount",
    "NumAromaticRings",
    "FractionCSP3",
    "HeavyAtomCount",
]

def _is_text_dtype(series: pd.Series) -> bool:
    """兼容 pandas 2.x（object）和 pandas 3.x（str）的字符串列判断。"""
    return series.dtype == object or pd.api.types.is_string_dtype(series)


_SMILES_CHARS = re.compile(r"^[A-Za-z0-9@+\-\[\]\(\)=#$/\\%.:*]+$")


def rdkit_available() -> bool:
    try:
        import rdkit  # noqa: F401

        return True
    except Exception:
        return False


def looks_like_smiles_column(name: str, series: pd.Series) -> bool:
    """按列名和取值判断一列是否是 SMILES。"""
    lname = str(name).strip().lower()
    if lname in {"smiles", "canonical_smiles", "smile", "smiles_string", "分子结构", "smiles式"}:
        return True
    if not _is_text_dtype(series):
        return False
    sample = series.dropna().astype(str).head(50)
    if len(sample) < 5:
        return False
    hits = 0
    for s in sample:
        s = s.strip()
        if " " in s or not _SMILES_CHARS.match(s):
            continue
        # 必须含有典型的有机元素/成键符号
        if re.search(r"(Cl|Br|[CNOSPF]|c1|=|\()", s):
            hits += 1
    return hits / len(sample) >= 0.9


def smiles_to_descriptors(smiles: pd.Series, prefix: str) -> pd.DataFrame:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors

    RDLogger.DisableLog("rdApp.*")
    funcs = {
        "MolWt": Descriptors.MolWt,
        "MolLogP": Descriptors.MolLogP,
        "TPSA": rdMolDescriptors.CalcTPSA,
        "NumHDonors": Lipinski.NumHDonors,
        "NumHAcceptors": Lipinski.NumHAcceptors,
        "NumRotatableBonds": Lipinski.NumRotatableBonds,
        "RingCount": Lipinski.RingCount,
        "NumAromaticRings": rdMolDescriptors.CalcNumAromaticRings,
        "FractionCSP3": rdMolDescriptors.CalcFractionCSP3,
        "HeavyAtomCount": Lipinski.HeavyAtomCount,
    }
    rows = []
    for s in smiles.astype(str).str.strip().tolist():
        mol = Chem.MolFromSmiles(s) if s and s.lower() != "nan" else None
        if mol is None:
            rows.append([np.nan] * len(funcs))
        else:
            rows.append([float(f(mol)) for f in funcs.values()])
    cols = [f"{prefix}_{n}" for n in funcs]
    return pd.DataFrame(rows, columns=cols, index=smiles.index)


class SmilesFeaturizer:
    """可序列化的特征化步骤：fit 时记录哪些列是 SMILES，transform 时展开。"""

    def __init__(self) -> None:
        self.smiles_columns: list[str] = []

    def fit(self, df: pd.DataFrame, smiles_columns: list[str]) -> "SmilesFeaturizer":
        self.smiles_columns = list(smiles_columns)
        if self.smiles_columns and not rdkit_available():
            raise RuntimeError(
                f"检测到 SMILES 分子结构列 {self.smiles_columns}，需要先安装 RDKit：pip install rdkit"
            )
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.smiles_columns:
            return df
        out = df.copy()
        for col in self.smiles_columns:
            if col not in out.columns:
                continue
            desc = smiles_to_descriptors(out[col], prefix=col)
            out = pd.concat([out.drop(columns=[col]), desc], axis=1)
        return out

    def output_columns(self, col: str) -> list[str]:
        return [f"{col}_{n}" for n in DESCRIPTOR_NAMES]
