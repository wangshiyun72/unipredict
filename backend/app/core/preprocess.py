"""自动数据画像 + 自动归一化。

用户只需要上传表格并指定目标列，这里自动完成：
1. 字段类型识别（数值 / 类别 / 日期 / SMILES 分子结构 / ID 列 / 常量列）
2. 任务类型判断（回归 / 分类）
3. 缺失值填充、类别编码
4. 归一化方式自动选择（StandardScaler / RobustScaler / MinMaxScaler），并生成归一化报告
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder, RobustScaler, StandardScaler

from .featurize import _is_text_dtype, looks_like_smiles_column, rdkit_available

SCALERS = {
    "standard": ("Z-score 标准化", StandardScaler),
    "minmax": ("Min-Max 归一化", MinMaxScaler),
    "robust": ("Robust 稳健缩放（中位数/四分位距）", RobustScaler),
    "none": ("不缩放", None),
}


# ---------------------------------------------------------------------------
# 读取文件
# ---------------------------------------------------------------------------
def read_table(path: str) -> pd.DataFrame:
    """读取 CSV / Excel，自动处理 UTF-8 / GBK 编码和分隔符。"""
    lower = str(path).lower()
    if lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    last_err: Exception | None = None
    for enc in ("utf-8-sig", "gbk", "gb18030", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc, sep=None, engine="python")
        except UnicodeDecodeError as e:
            last_err = e
            continue
    raise ValueError(f"无法识别文件编码：{last_err}")


# ---------------------------------------------------------------------------
# 字段类型识别
# ---------------------------------------------------------------------------
def _is_datetime(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if not _is_text_dtype(series):
        return False
    sample = series.dropna().astype(str).head(30)
    if len(sample) < 5:
        return False
    # 必须包含日期分隔符，避免把纯数字误判为日期
    if not sample.str.contains(r"\d{1,4}[-/年.]\d{1,2}", regex=True).mean() > 0.8:
        return False
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    return parsed.notna().mean() > 0.9


def infer_column_type(name: str, series: pd.Series, n_rows: int) -> str:
    non_null = series.dropna()
    if len(non_null) == 0:
        return "empty"
    if non_null.nunique() <= 1:
        return "constant"
    if looks_like_smiles_column(name, series):
        return "smiles"
    if pd.api.types.is_bool_dtype(series):
        return "categorical"
    if pd.api.types.is_numeric_dtype(series):
        # 连续整数且全部唯一，并且列名像编号 → ID 列
        lname = str(name).lower()
        if non_null.nunique() == n_rows and any(k in lname for k in ("id", "编号", "序号", "index")):
            return "id"
        return "numeric"
    if _is_datetime(series):
        return "datetime"
    # 字符串：尝试转数值（例如带空格的数字）
    converted = pd.to_numeric(non_null.astype(str).str.strip(), errors="coerce")
    if converted.notna().mean() > 0.95:
        return "numeric"
    nunique = non_null.nunique()
    if nunique == len(non_null) and nunique > 20:
        return "id"
    if nunique > max(50, 0.5 * len(non_null)):
        return "text"  # 高基数自由文本，暂不使用
    return "categorical"


def profile_dataframe(df: pd.DataFrame) -> list[dict[str, Any]]:
    """数据画像：每列的类型、缺失率、取值统计，供前端展示与目标列选择。"""
    n = len(df)
    profile = []
    for col in df.columns:
        s = df[col]
        ctype = infer_column_type(col, s, n)
        item: dict[str, Any] = {
            "name": str(col),
            "type": ctype,
            "missing": int(s.isna().sum()),
            "missing_rate": round(float(s.isna().mean()), 4) if n else 0.0,
            "unique": int(s.nunique(dropna=True)),
        }
        if ctype == "numeric":
            num = pd.to_numeric(s, errors="coerce")
            item.update(
                {
                    "mean": _f(num.mean()),
                    "std": _f(num.std()),
                    "min": _f(num.min()),
                    "max": _f(num.max()),
                    "median": _f(num.median()),
                }
            )
        elif ctype in ("categorical", "text", "id", "smiles"):
            item["top_values"] = [str(v) for v in s.dropna().astype(str).value_counts().head(8).index]
        profile.append(item)
    return profile


def _f(x: Any) -> float | None:
    try:
        v = float(x)
        return None if np.isnan(v) or np.isinf(v) else round(v, 6)
    except Exception:
        return None


def infer_task(y: pd.Series) -> str:
    """判断任务类型：非数值目标或少量离散整数 → 分类，否则 → 回归。"""
    y = y.dropna()
    if not pd.api.types.is_numeric_dtype(y):
        converted = pd.to_numeric(y, errors="coerce")
        if converted.notna().mean() < 0.95:
            return "classification"
        y = converted.dropna()
    nunique = y.nunique()
    is_integer = np.allclose(y, np.round(y))
    if nunique <= 2:
        return "classification"
    if is_integer and nunique <= 10 and nunique / max(len(y), 1) < 0.05:
        return "classification"
    return "regression"


# ---------------------------------------------------------------------------
# 自动归一化
# ---------------------------------------------------------------------------
def choose_scaler(df_num: pd.DataFrame) -> tuple[str, str]:
    """自动选择缩放方式，并返回选择理由。

    规则：
    - 有明显离群值（IQR 规则下离群点占比 > 5% 的列超过 1/3）→ RobustScaler
    - 所有列都有天然上下界且分布较均匀（如 0~1、百分比）→ MinMaxScaler
    - 其他情况 → StandardScaler
    """
    if df_num.shape[1] == 0:
        return "none", "没有数值特征，无需缩放"
    outlier_cols = 0
    bounded_cols = 0
    for col in df_num.columns:
        s = pd.to_numeric(df_num[col], errors="coerce").dropna()
        if len(s) < 5:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr > 0:
            ratio = ((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).mean()
            if ratio > 0.05:
                outlier_cols += 1
        if s.min() >= 0 and (s.max() <= 1 or s.max() <= 100) and abs(s.skew()) < 0.5:
            bounded_cols += 1
    n = df_num.shape[1]
    if outlier_cols >= max(1, n / 3):
        return "robust", f"{outlier_cols}/{n} 个数值特征存在明显离群值（IQR 规则离群比例 > 5%），选用稳健缩放"
    if bounded_cols == n:
        return "minmax", "所有数值特征都有固定上下界且分布较均匀，选用 Min-Max 归一化"
    return "standard", "数值特征量纲不一，选用 Z-score 标准化（均值 0、方差 1）"


class DateExpander:
    """把日期列展开成 年/月/日/星期 数值特征。"""

    def __init__(self, columns: list[str]):
        self.columns = columns

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.columns:
            return df
        out = df.copy()
        for col in self.columns:
            if col not in out.columns:
                continue
            dt = pd.to_datetime(out[col], errors="coerce", format="mixed")
            out[f"{col}_year"] = dt.dt.year
            out[f"{col}_month"] = dt.dt.month
            out[f"{col}_day"] = dt.dt.day
            out[f"{col}_weekday"] = dt.dt.weekday
            out = out.drop(columns=[col])
        return out


class AutoPreprocessor:
    """自动预处理器：fit 时根据训练数据确定每一列的处理方式，之后对预测数据复用同样的变换。"""

    def __init__(self, scaler: str = "auto") -> None:
        self.scaler_option = scaler
        self.scaler_used = "none"
        self.scaler_reason = ""
        self.input_columns: list[str] = []
        self.column_types: dict[str, str] = {}
        self.numeric_cols: list[str] = []
        self.categorical_cols: list[str] = []
        self.datetime_cols: list[str] = []
        self.smiles_cols: list[str] = []
        self.dropped: dict[str, str] = {}
        self.date_expander: DateExpander | None = None
        self.transformer: ColumnTransformer | None = None
        self.feature_names_out: list[str] = []
        self.normalization_report: list[dict[str, Any]] = []
        self.input_schema: list[dict[str, Any]] = []

    # 第一步：只做字段识别（SMILES 列需要在 featurize 之后才进入数值处理）
    def analyze(self, X: pd.DataFrame) -> None:
        n = len(X)
        self.input_columns = [str(c) for c in X.columns]
        for col in X.columns:
            t = infer_column_type(col, X[col], n)
            self.column_types[str(col)] = t
            if t == "numeric":
                self.numeric_cols.append(str(col))
            elif t == "categorical":
                self.categorical_cols.append(str(col))
            elif t == "datetime":
                self.datetime_cols.append(str(col))
            elif t == "smiles":
                if rdkit_available():
                    self.smiles_cols.append(str(col))
                else:
                    self.dropped[str(col)] = "SMILES 分子结构列（未安装 RDKit，暂不使用；pip install rdkit 后可自动提取分子描述符）"
            else:
                reason = {
                    "id": "疑似编号/ID 列，与预测无关",
                    "constant": "常量列，没有信息量",
                    "empty": "整列为空",
                    "text": "高基数自由文本，暂不支持",
                }.get(t, t)
                self.dropped[str(col)] = reason
        self.input_schema = self._build_input_schema(X)

    def _build_input_schema(self, X: pd.DataFrame) -> list[dict[str, Any]]:
        schema = []
        for col in self.input_columns:
            t = self.column_types[col]
            if col in self.dropped:
                continue
            item: dict[str, Any] = {"name": col, "type": t}
            s = X[col]
            if t == "numeric":
                num = pd.to_numeric(s, errors="coerce")
                item.update({"min": _f(num.min()), "max": _f(num.max()), "default": _f(num.median())})
            elif t == "categorical":
                vals = [str(v) for v in s.dropna().astype(str).value_counts().index[:50]]
                item.update({"choices": vals, "default": vals[0] if vals else ""})
            elif t in ("smiles", "datetime"):
                first = s.dropna().astype(str)
                item["default"] = first.iloc[0] if len(first) else ""
            schema.append(item)
        return schema

    def _coerce(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        X.columns = [str(c) for c in X.columns]
        missing = [c for c in self.input_columns if c not in X.columns and c not in self.dropped]
        if missing:
            raise ValueError(f"输入数据缺少字段：{missing}")
        X = X[[c for c in self.input_columns if c in X.columns]]
        X = X.drop(columns=[c for c in self.dropped if c in X.columns])
        for col in self.numeric_cols:
            X[col] = pd.to_numeric(X[col], errors="coerce")
        for col in self.categorical_cols:
            X[col] = X[col].astype(str).where(X[col].notna(), np.nan)
        return X

    # 第二步：在（已特征化的）数据上拟合
    def fit(self, X_feat: pd.DataFrame, extra_numeric: list[str]) -> "AutoPreprocessor":
        X_feat = X_feat.copy()
        self.date_expander = DateExpander(self.datetime_cols)
        X_feat = self.date_expander.transform(X_feat)
        date_cols = [c for c in X_feat.columns if any(c.startswith(f"{d}_") for d in self.datetime_cols)]
        num_cols = self.numeric_cols + extra_numeric + date_cols
        num_cols = [c for c in num_cols if c in X_feat.columns]

        if self.scaler_option == "auto":
            self.scaler_used, self.scaler_reason = choose_scaler(X_feat[num_cols])
        else:
            self.scaler_used = self.scaler_option
            self.scaler_reason = "用户手动指定"

        scaler_cls = SCALERS[self.scaler_used][1]
        num_steps: list[tuple[str, Any]] = [("impute", SimpleImputer(strategy="median"))]
        if scaler_cls is not None:
            num_steps.append(("scale", scaler_cls()))
        transformers: list[tuple[str, Any, list[str]]] = []
        if num_cols:
            transformers.append(("num", Pipeline(num_steps), num_cols))
        if self.categorical_cols:
            transformers.append(
                (
                    "cat",
                    Pipeline(
                        [
                            ("impute", SimpleImputer(strategy="most_frequent")),
                            (
                                "onehot",
                                OneHotEncoder(handle_unknown="ignore", max_categories=30, sparse_output=False),
                            ),
                        ]
                    ),
                    self.categorical_cols,
                )
            )
        if not transformers:
            raise ValueError("没有可用的特征列，请检查数据（可能全部被识别为 ID/常量/文本列）")
        self.transformer = ColumnTransformer(transformers, remainder="drop", verbose_feature_names_out=False)
        self.transformer.fit(X_feat)
        self.feature_names_out = [str(n) for n in self.transformer.get_feature_names_out()]
        self._build_report(X_feat, num_cols)
        return self

    def _build_report(self, X_feat: pd.DataFrame, num_cols: list[str]) -> None:
        report = []
        for col in num_cols:
            s = pd.to_numeric(X_feat[col], errors="coerce")
            report.append(
                {
                    "column": col,
                    "method": SCALERS[self.scaler_used][0],
                    "missing_filled": int(s.isna().sum()),
                    "fill_value": _f(s.median()),
                    "before_mean": _f(s.mean()),
                    "before_std": _f(s.std()),
                    "before_min": _f(s.min()),
                    "before_max": _f(s.max()),
                }
            )
        for col in self.categorical_cols:
            report.append(
                {
                    "column": col,
                    "method": "One-Hot 独热编码",
                    "missing_filled": int(X_feat[col].isna().sum()),
                    "categories": int(X_feat[col].nunique()),
                }
            )
        self.normalization_report = report

    def transform(self, X_feat: pd.DataFrame) -> np.ndarray:
        assert self.transformer is not None and self.date_expander is not None
        X_feat = self.date_expander.transform(X_feat)
        return np.asarray(self.transformer.transform(X_feat), dtype=np.float32)

    def summary(self) -> dict[str, Any]:
        return {
            "scaler": self.scaler_used,
            "scaler_name": SCALERS[self.scaler_used][0],
            "scaler_reason": self.scaler_reason,
            "column_types": self.column_types,
            "dropped_columns": self.dropped,
            "n_features_out": len(self.feature_names_out),
            "report": self.normalization_report,
        }
