"""数据模板：面向化工/环境领域的预置预测场景。

每个模板包含：字段说明（含单位）、目标列、任务类型、示例数据、应用场景说明、可下载的 CSV 填写模板。
跨学科用户按模板整理自己的数据即可直接上传预测。

数据来源：
- aquatic_toxicity：UCI QSAR fish toxicity 公开数据集（Cassotti et al., 2015）
- solubility：ESOL / Delaney 公开数据集（Delaney, J. Chem. Inf. Comput. Sci., 2004）
- effluent_quality、reaction_yield：依据反应动力学规律生成的模拟数据，仅用于功能演示，
  可替换为实验室实测数据
"""
from __future__ import annotations

import io
import logging
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import settings

logger = logging.getLogger(__name__)

TEMPLATES: dict[str, dict[str, Any]] = {
    "aquatic_toxicity": {
        "key": "aquatic_toxicity",
        "name": "新污染物水生毒性预测",
        "domain": "环境毒理",
        "icon": "fish",
        "task": "regression",
        "target": "LC50",
        "description": "根据分子描述符预测化合物对黑头呆鱼（Pimephales promelas）96 小时急性毒性 LC50，"
        "用于新污染物（如轮胎源污染物、农药、药物残留）的生态风险快速筛查。",
        "scenario": "环境科学课题组在新污染物筛查中，对尚无实测毒性数据的化合物先用模型给出毒性估计，"
        "优先对高毒性候选物开展实验验证，减少动物实验和测试成本。",
        "source": "UCI Machine Learning Repository：QSAR fish toxicity（Cassotti et al., 2015），908 个化合物",
        "source_url": "https://archive.ics.uci.edu/dataset/504/qsar+fish+toxicity",
        "simulated": False,
        "columns": [
            {"name": "CIC0", "unit": "-", "desc": "信息指数（邻域对称性，0 阶）"},
            {"name": "SM1_Dz", "unit": "-", "desc": "基于 Barysz 矩阵（原子序数加权）的谱矩"},
            {"name": "GATS1i", "unit": "-", "desc": "Geary 自相关描述符（电离势加权，lag 1）"},
            {"name": "NdsCH", "unit": "个", "desc": "=CH- 原子类型计数"},
            {"name": "NdssC", "unit": "个", "desc": "=C< 原子类型计数"},
            {"name": "MLOGP", "unit": "-", "desc": "Moriguchi 辛醇-水分配系数（疏水性）"},
            {"name": "LC50", "unit": "-log(mol/L)", "desc": "96h 半致死浓度（目标列，数值越大毒性越强）", "target": True},
        ],
        "recommended_models": ["tabpfn", "hist_gb", "random_forest", "resmlp"],
    },
    "effluent_quality": {
        "key": "effluent_quality",
        "name": "废水处理出水水质预测",
        "domain": "水处理工程",
        "icon": "water",
        "task": "regression",
        "target": "COD去除率",
        "description": "根据磁控-生物协同曝气生物滤池（BAF）的进水水质与运行参数，预测 COD 去除率"
        "（数据中同时提供氨氮去除率，可作为另一个目标列）。",
        "scenario": "污水处理/中试装置运行人员输入当天的进水水质和运行条件，提前预估出水能否达标，"
        "并通过可解释性结果找到影响去除效果的关键运行参数（如 HRT、溶解氧、磁场强度）。",
        "source": "模拟数据：依据生物膜反应动力学与温度、pH、溶解氧影响规律生成，仅用于功能演示，可替换为实验室实测数据",
        "source_url": "",
        "simulated": True,
        "columns": [
            {"name": "进水COD", "unit": "mg/L", "desc": "进水化学需氧量"},
            {"name": "进水氨氮", "unit": "mg/L", "desc": "进水 NH4+-N"},
            {"name": "农药浓度", "unit": "mg/L", "desc": "进水特征农药污染物浓度"},
            {"name": "HRT", "unit": "h", "desc": "水力停留时间"},
            {"name": "温度", "unit": "℃", "desc": "反应器水温"},
            {"name": "pH", "unit": "-", "desc": "进水 pH"},
            {"name": "溶解氧", "unit": "mg/L", "desc": "反应器溶解氧 DO"},
            {"name": "气水比", "unit": "-", "desc": "曝气量与进水量之比"},
            {"name": "磁场强度", "unit": "mT", "desc": "外加磁场强度（0 表示未加磁场）"},
            {"name": "运行天数", "unit": "d", "desc": "反应器启动后的运行天数（反映生物膜成熟度）"},
            {"name": "COD去除率", "unit": "%", "desc": "COD 去除率（目标列）", "target": True},
            {"name": "氨氮去除率", "unit": "%", "desc": "氨氮去除率（可选的另一个目标列，训练 COD 时会被当作特征，建议删除）"},
        ],
        "drop_for_training": ["氨氮去除率"],
        "recommended_models": ["tabpfn", "hist_gb", "random_forest", "ft_transformer"],
    },
    "solubility": {
        "key": "solubility",
        "name": "化合物水溶解度预测",
        "domain": "物理化学",
        "icon": "flask",
        "task": "regression",
        "target": "logS",
        "description": "根据分子结构（SMILES）和基本分子性质预测化合物在水中的溶解度 logS。"
        "安装 RDKit 后平台会自动从 SMILES 中提取分子描述符。",
        "scenario": "化工/制药课题组在合成或筛选化合物前预估其水溶性，用于溶剂选择、分离工艺设计"
        "和污染物环境迁移性评估。",
        "source": "ESOL / Delaney 公开数据集（J. Chem. Inf. Comput. Sci. 2004, 44, 1000），1128 个化合物",
        "source_url": "https://pubs.acs.org/doi/10.1021/ci034243x",
        "simulated": False,
        "columns": [
            {"name": "smiles", "unit": "-", "desc": "分子结构 SMILES 字符串（安装 RDKit 后自动特征化）"},
            {"name": "分子量", "unit": "g/mol", "desc": "Molecular Weight"},
            {"name": "氢键供体数", "unit": "个", "desc": "Number of H-Bond Donors"},
            {"name": "环数", "unit": "个", "desc": "Number of Rings"},
            {"name": "可旋转键数", "unit": "个", "desc": "Number of Rotatable Bonds"},
            {"name": "极性表面积", "unit": "Å²", "desc": "Polar Surface Area"},
            {"name": "最小度", "unit": "-", "desc": "Minimum Degree（分子图最小顶点度）"},
            {"name": "logS", "unit": "log(mol/L)", "desc": "实测水溶解度（目标列）", "target": True},
        ],
        "recommended_models": ["tabpfn", "hist_gb", "random_forest", "resmlp"],
    },
    "reaction_yield": {
        "key": "reaction_yield",
        "name": "反应条件→产物收率预测",
        "domain": "化学反应工程",
        "icon": "reaction",
        "task": "regression",
        "target": "收率",
        "description": "根据反应温度、时间、催化剂用量、底物配比、溶剂和碱的种类预测产物收率，"
        "辅助反应条件优化，减少试错实验次数。",
        "scenario": "合成实验室在条件筛选阶段，用已有几十组实验结果训练模型，预测未做过的条件组合的收率，"
        "并结合特征重要性判断哪个条件对收率影响最大，指导下一轮实验设计。",
        "source": "模拟数据：依据温度最优区间、时间饱和效应、催化剂与溶剂效应规律生成，仅用于功能演示，可替换为实验室实测数据",
        "source_url": "",
        "simulated": True,
        "columns": [
            {"name": "反应温度", "unit": "℃", "desc": "反应温度"},
            {"name": "反应时间", "unit": "h", "desc": "反应时间"},
            {"name": "催化剂用量", "unit": "mol%", "desc": "催化剂摩尔分数"},
            {"name": "底物摩尔比", "unit": "-", "desc": "试剂 B 与底物 A 的摩尔比"},
            {"name": "溶剂", "unit": "类别", "desc": "乙醇 / 甲苯 / DMF / 水 / 乙腈"},
            {"name": "碱", "unit": "类别", "desc": "K2CO3 / Cs2CO3 / Et3N / 无"},
            {"name": "收率", "unit": "%", "desc": "分离收率（目标列）", "target": True},
        ],
        "recommended_models": ["tabpfn", "hist_gb", "random_forest", "linear"],
    },
}


def template_path(key: str) -> Path:
    return Path(settings.TEMPLATE_DATA_DIR) / f"{key}.csv"


# ---------------------------------------------------------------------------
# 模拟数据生成
# ---------------------------------------------------------------------------
def _gen_effluent(n: int = 600, seed: int = 2025) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cod_in = rng.uniform(200, 800, n)
    nh_in = rng.uniform(20, 80, n)
    pest = rng.uniform(0, 50, n)
    hrt = rng.uniform(2, 12, n)
    temp = rng.uniform(10, 35, n)
    ph = rng.uniform(6.0, 9.0, n)
    do = rng.uniform(1.0, 6.0, n)
    gw = rng.uniform(2, 10, n)
    mag = rng.choice([0, 0, 10, 20, 30, 40, 50, 60], n) + rng.normal(0, 1, n).clip(-1, 1)
    mag = np.clip(mag, 0, None)
    days = rng.integers(1, 181, n)

    f_hrt = 1 - np.exp(-0.32 * hrt)
    f_temp = np.exp(-((temp - 28) / 14) ** 2)
    f_ph = np.exp(-((ph - 7.4) / 1.3) ** 2)
    f_do = do / (do + 1.2)
    f_load = 1 - 0.00025 * (cod_in - 200)
    f_pest = 1 - 0.0055 * pest
    f_mag = 1 + 0.18 * (mag / 30) * np.exp(1 - mag / 30)  # 适度磁场促进，过强抑制
    f_days = 1 - 0.35 * np.exp(-days / 25)
    f_gw = 1 - 0.08 * np.abs(gw - 6) / 4
    cod_rm = 100 * f_hrt * (0.55 + 0.45 * f_temp) * (0.6 + 0.4 * f_ph) * (0.5 + 0.5 * f_do) * f_load * f_pest * f_mag * f_days * f_gw
    cod_rm = np.clip(cod_rm * 1.18 + rng.normal(0, 2.5, n), 5, 99)

    f_nit_temp = np.exp(-((temp - 30) / 9) ** 2)  # 硝化对温度更敏感
    nh_rm = 100 * (1 - np.exp(-0.25 * hrt)) * (0.3 + 0.7 * f_nit_temp) * (do / (do + 2.0)) * f_ph * f_days * (1 - 0.007 * pest) * f_mag
    nh_rm = np.clip(nh_rm * 1.45 + rng.normal(0, 3, n), 3, 99)

    df = pd.DataFrame(
        {
            "进水COD": cod_in.round(1), "进水氨氮": nh_in.round(2), "农药浓度": pest.round(2), "HRT": hrt.round(2),
            "温度": temp.round(1), "pH": ph.round(2), "溶解氧": do.round(2), "气水比": gw.round(1),
            "磁场强度": mag.round(1), "运行天数": days, "COD去除率": cod_rm.round(2), "氨氮去除率": nh_rm.round(2),
        }
    )
    # 模拟真实监测数据中的少量缺失
    for col in ("溶解氧", "pH"):
        df.loc[rng.choice(n, size=int(n * 0.02), replace=False), col] = np.nan
    return df


def _gen_yield(n: int = 400, seed: int = 2025) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    T = rng.uniform(40, 120, n)
    t = rng.uniform(0.5, 12, n)
    cat = rng.uniform(0.5, 10, n)
    ratio = rng.uniform(0.8, 3.0, n)
    solvents = np.array(["乙醇", "甲苯", "DMF", "水", "乙腈"])
    bases = np.array(["K2CO3", "Cs2CO3", "Et3N", "无"])
    sol = rng.choice(solvents, n)
    base = rng.choice(bases, n)
    sol_eff = pd.Series(sol).map({"乙醇": 0.85, "甲苯": 0.7, "DMF": 1.0, "水": 0.45, "乙腈": 0.9}).to_numpy()
    base_eff = pd.Series(base).map({"K2CO3": 0.92, "Cs2CO3": 1.0, "Et3N": 0.8, "无": 0.4}).to_numpy()
    f_T = np.exp(-((T - 88) / 25) ** 2) - 0.004 * np.clip(T - 100, 0, None) * t  # 高温长时间副反应
    f_t = 1 - np.exp(-t / 2.5)
    f_cat = cat / (cat + 1.5)
    f_ratio = np.exp(-((ratio - 1.6) / 1.0) ** 2)
    y = 140 * np.clip(f_T, 0, 1) * f_t * f_cat * (0.6 + 0.4 * f_ratio) * sol_eff * base_eff
    y = np.clip(y + rng.normal(0, 2.5, n), 0, 97)
    return pd.DataFrame(
        {"反应温度": T.round(1), "反应时间": t.round(2), "催化剂用量": cat.round(2), "底物摩尔比": ratio.round(2),
         "溶剂": sol, "碱": base, "收率": y.round(1)}
    )


# ---------------------------------------------------------------------------
# 公开数据下载
# ---------------------------------------------------------------------------
TOX_URLS = [
    "https://archive.ics.uci.edu/ml/machine-learning-databases/00504/qsar_fish_toxicity.csv",
    "https://archive.ics.uci.edu/static/public/504/qsar+fish+toxicity.zip",
]
ESOL_URLS = [
    "https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/delaney-processed.csv",
    "https://raw.githubusercontent.com/deepchem/deepchem/master/datasets/delaney-processed.csv",
]


def _download(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 UniPredict"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _get_toxicity() -> pd.DataFrame:
    cols = ["CIC0", "SM1_Dz", "GATS1i", "NdsCH", "NdssC", "MLOGP", "LC50"]
    last: Exception | None = None
    for url in TOX_URLS:
        try:
            data = _download(url)
            if url.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    name = [n for n in z.namelist() if n.endswith(".csv")][0]
                    data = z.read(name)
            df = pd.read_csv(io.BytesIO(data), sep=";", header=None)
            df.columns = cols
            return df
        except Exception as e:
            last = e
            logger.warning("下载 %s 失败：%s", url, e)
    raise RuntimeError(f"毒性数据下载失败（{last}）。可手动下载 qsar_fish_toxicity.csv 放到 {template_path('aquatic_toxicity')}")


def _get_esol() -> pd.DataFrame:
    last: Exception | None = None
    for url in ESOL_URLS:
        try:
            df = pd.read_csv(io.BytesIO(_download(url)))
            rename = {
                "smiles": "smiles",
                "Molecular Weight": "分子量",
                "Number of H-Bond Donors": "氢键供体数",
                "Number of Rings": "环数",
                "Number of Rotatable Bonds": "可旋转键数",
                "Polar Surface Area": "极性表面积",
                "Minimum Degree": "最小度",
                "measured log solubility in mols per litre": "logS",
            }
            df = df[[c for c in rename if c in df.columns]].rename(columns=rename)
            return df[["smiles", "分子量", "氢键供体数", "环数", "可旋转键数", "极性表面积", "最小度", "logS"]]
        except Exception as e:
            last = e
            logger.warning("下载 %s 失败：%s", url, e)
    raise RuntimeError(f"溶解度数据下载失败（{last}）。可手动下载 delaney-processed.csv 后运行 scripts/prepare_templates.py --esol 文件路径")


GENERATORS = {
    "aquatic_toxicity": _get_toxicity,
    "effluent_quality": _gen_effluent,
    "solubility": _get_esol,
    "reaction_yield": _gen_yield,
}


# 随代码一起分发的公开数据集副本（服务器无法访问国外数据源时使用）
BUNDLED_DIR = Path(__file__).resolve().parent.parent / "data" / "templates"


def ensure_template_data(key: str) -> Path:
    if key not in TEMPLATES:
        raise KeyError(f"未知模板：{key}")
    path = template_path(key)
    if not path.exists():
        bundled = BUNDLED_DIR / f"{key}.csv"
        if bundled.exists():
            path.write_bytes(bundled.read_bytes())
        else:
            df = GENERATORS[key]()
            df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def template_status(key: str) -> dict[str, Any]:
    path = template_path(key)
    info: dict[str, Any] = {"ready": path.exists()}
    if path.exists():
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            info.update({"n_rows": int(len(df)), "n_cols": int(df.shape[1])})
        except Exception:
            info["ready"] = False
    return info


def list_templates() -> list[dict[str, Any]]:
    return [{**t, **template_status(k)} for k, t in TEMPLATES.items()]


def blank_template_csv(key: str) -> bytes:
    """可下载的填写模板：表头 + 字段说明行 + 3 条示例数据。"""
    t = TEMPLATES[key]
    cols = [c["name"] for c in t["columns"]]
    rows: list[list[Any]] = []
    try:
        df = pd.read_csv(ensure_template_data(key), encoding="utf-8-sig")
        rows = df[cols].head(3).values.tolist()
    except Exception:
        pass
    out = io.StringIO()
    pd.DataFrame(rows, columns=cols).to_csv(out, index=False)
    return out.getvalue().encode("utf-8-sig")


def prepare_all() -> dict[str, str]:
    res = {}
    for key in TEMPLATES:
        try:
            ensure_template_data(key)
            res[key] = "ok"
        except Exception as e:
            res[key] = f"失败：{e}"
    return res
