"""深度学习模型适配器（PyTorch）。

- ResMLP：带残差连接、BatchNorm 和 Dropout 的多层感知机
- FT-Transformer：特征分词 + Transformer 编码器（Gorishniy et al., NeurIPS 2021），表格深度学习的常用强基线

两个模型都支持 GPU 训练、早停、记录训练/验证损失曲线（用于前端可视化）。
"""
from __future__ import annotations

import copy
from typing import Any

import numpy as np

from ..runtime import get_device, gpu_slot
from .base import FAMILY_DEEP, ModelAdapter, register_adapter


def _build_resmlp(n_in: int, n_out: int, hidden: int, n_blocks: int, dropout: float):
    import torch.nn as nn

    class Block(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.net = nn.Sequential(
                nn.BatchNorm1d(hidden),
                nn.Linear(hidden, hidden),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(hidden, hidden),
            )

        def forward(self, x):
            return x + self.net(x)

    class ResMLP(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.inp = nn.Linear(n_in, hidden)
            self.blocks = nn.Sequential(*[Block() for _ in range(n_blocks)])
            self.out = nn.Sequential(nn.BatchNorm1d(hidden), nn.GELU(), nn.Linear(hidden, n_out))

        def forward(self, x):
            return self.out(self.blocks(self.inp(x)))

    return ResMLP()


def _build_ft_transformer(n_in: int, n_out: int, d_token: int, n_layers: int, n_heads: int, dropout: float):
    import torch
    import torch.nn as nn

    class FTTransformer(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            # 每个数值特征一个 token：x_i * W_i + b_i
            self.weight = nn.Parameter(torch.randn(n_in, d_token) * 0.02)
            self.bias = nn.Parameter(torch.zeros(n_in, d_token))
            self.cls = nn.Parameter(torch.zeros(1, 1, d_token))
            layer = nn.TransformerEncoderLayer(
                d_model=d_token,
                nhead=n_heads,
                dim_feedforward=d_token * 2,
                dropout=dropout,
                batch_first=True,
                norm_first=True,
                activation="gelu",
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=n_layers)
            self.head = nn.Sequential(nn.LayerNorm(d_token), nn.ReLU(), nn.Linear(d_token, n_out))

        def forward(self, x):
            tokens = x.unsqueeze(-1) * self.weight + self.bias  # (B, F, D)
            cls = self.cls.expand(x.shape[0], -1, -1)
            h = self.encoder(torch.cat([cls, tokens], dim=1))
            return self.head(h[:, 0])

    return FTTransformer()


class _TorchAdapter(ModelAdapter):
    family = FAMILY_DEEP
    requires = ("torch",)
    uses_gpu = True

    def build_module(self, n_in: int, n_out: int):  # pragma: no cover
        raise NotImplementedError

    # ---------------------------- 训练 ----------------------------
    def fit(self, X: np.ndarray, y: np.ndarray) -> "_TorchAdapter":
        import torch
        import torch.nn as nn

        torch.manual_seed(self.random_state)
        rng = np.random.default_rng(self.random_state)
        X = np.asarray(X, dtype=np.float32)
        self.n_in = X.shape[1]
        if self.task == "classification":
            y = np.asarray(y).astype(np.int64)
            self.n_classes_ = int(y.max()) + 1
            self.n_out = self.n_classes_
            self.y_mean, self.y_std = 0.0, 1.0
        else:
            y = np.asarray(y, dtype=np.float32)
            self.y_mean, self.y_std = float(y.mean()), float(y.std() or 1.0)
            y = (y - self.y_mean) / self.y_std  # 目标值也做标准化，训练更稳定
            self.n_out = 1

        # 划出 15% 作为早停验证集
        idx = rng.permutation(len(X))
        n_val = max(1, int(len(X) * 0.15)) if len(X) >= 20 else 0
        val_idx, tr_idx = idx[:n_val], idx[n_val:]

        device = get_device()
        with gpu_slot(device == "cuda"):
            module = self.build_module(self.n_in, self.n_out).to(device)
            opt = torch.optim.AdamW(module.parameters(), lr=float(self.params["lr"]), weight_decay=1e-4)
            loss_fn: Any = nn.CrossEntropyLoss() if self.task == "classification" else nn.MSELoss()
            Xt = torch.tensor(X, device=device)
            yt = torch.tensor(y, device=device)
            if self.task == "regression":
                yt = yt.view(-1, 1)
            bs = int(self.params["batch_size"])
            epochs = int(self.params["epochs"])
            patience = int(self.params.get("patience", 20))
            best_state, best_val, bad = None, float("inf"), 0
            self.history: dict[str, list[float]] = {"train_loss": [], "val_loss": []}
            for _epoch in range(epochs):
                module.train()
                perm = torch.tensor(rng.permutation(tr_idx), device=device)
                total = 0.0
                for start in range(0, len(perm), bs):
                    b = perm[start : start + bs]
                    if len(b) < 2:
                        continue  # BatchNorm 需要 batch>1
                    opt.zero_grad()
                    loss = loss_fn(module(Xt[b]), yt[b])
                    loss.backward()
                    opt.step()
                    total += float(loss.item()) * len(b)
                self.history["train_loss"].append(round(total / max(len(tr_idx), 1), 6))
                if n_val:
                    module.eval()
                    with torch.no_grad():
                        vb = torch.tensor(val_idx, device=device)
                        vloss = float(loss_fn(module(Xt[vb]), yt[vb]).item())
                    self.history["val_loss"].append(round(vloss, 6))
                    if vloss < best_val - 1e-6:
                        best_val, bad = vloss, 0
                        best_state = copy.deepcopy({k: v.detach().cpu() for k, v in module.state_dict().items()})
                    else:
                        bad += 1
                        if bad >= patience:
                            break
            if best_state is not None:
                module.load_state_dict(best_state)
            self.state_dict_ = {k: v.detach().cpu() for k, v in module.state_dict().items()}
            self.epochs_trained = len(self.history["train_loss"])
        self._module = None  # 推理时按需在目标设备上重建
        return self

    # ---------------------------- 推理 ----------------------------
    def _get_module(self, device: str):
        if getattr(self, "_module", None) is None or getattr(self, "_module_device", None) != device:
            module = self.build_module(self.n_in, self.n_out)
            module.load_state_dict(self.state_dict_)
            module.to(device).eval()
            self._module, self._module_device = module, device
        return self._module

    def _forward(self, X: np.ndarray) -> np.ndarray:
        import torch

        device = get_device()
        with gpu_slot(device == "cuda"):
            module = self._get_module(device)
            outs = []
            with torch.no_grad():
                for start in range(0, len(X), 4096):
                    xb = torch.tensor(np.asarray(X[start : start + 4096], dtype=np.float32), device=device)
                    outs.append(module(xb).float().cpu().numpy())
        return np.concatenate(outs, axis=0) if outs else np.zeros((0, self.n_out))

    def predict(self, X: np.ndarray) -> np.ndarray:
        out = self._forward(X)
        if self.task == "classification":
            return out.argmax(axis=1)
        return out[:, 0] * self.y_std + self.y_mean

    def predict_proba(self, X: np.ndarray) -> np.ndarray | None:
        if self.task != "classification":
            return None
        logits = self._forward(X)
        logits = logits - logits.max(axis=1, keepdims=True)
        p = np.exp(logits)
        return p / p.sum(axis=1, keepdims=True)

    # 序列化时不保存 nn.Module 对象本身，只保存权重
    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        state["_module"] = None
        state.pop("_module_device", None)
        return state


@register_adapter
class ResMLPAdapter(_TorchAdapter):
    key = "resmlp"
    name = "深度残差 MLP"
    description = "带残差连接的多层感知机，支持 GPU 训练与早停，适合数千样本以上的数据。"
    param_spec = [
        {"name": "hidden", "label": "隐藏层宽度", "type": "int", "default": 128, "min": 16, "max": 1024},
        {"name": "n_blocks", "label": "残差块数", "type": "int", "default": 3, "min": 1, "max": 12},
        {"name": "dropout", "label": "Dropout", "type": "float", "default": 0.1, "min": 0, "max": 0.7},
        {"name": "lr", "label": "学习率", "type": "float", "default": 0.001, "min": 0.00001, "max": 0.1},
        {"name": "epochs", "label": "最大轮数", "type": "int", "default": 300, "min": 5, "max": 3000},
        {"name": "batch_size", "label": "批大小", "type": "int", "default": 128, "min": 8, "max": 4096},
        {"name": "patience", "label": "早停耐心", "type": "int", "default": 30, "min": 3, "max": 500},
    ]

    def build_module(self, n_in: int, n_out: int):
        return _build_resmlp(
            n_in, n_out, int(self.params["hidden"]), int(self.params["n_blocks"]), float(self.params["dropout"])
        )


@register_adapter
class FTTransformerAdapter(_TorchAdapter):
    key = "ft_transformer"
    name = "FT-Transformer"
    description = "把每个特征当作一个 token 输入 Transformer 编码器，是表格数据深度学习的代表性模型。"
    quick_default = False
    param_spec = [
        {"name": "d_token", "label": "Token 维度", "type": "int", "default": 64, "min": 16, "max": 256},
        {"name": "n_layers", "label": "Transformer 层数", "type": "int", "default": 3, "min": 1, "max": 8},
        {"name": "n_heads", "label": "注意力头数", "type": "int", "default": 8, "min": 1, "max": 16},
        {"name": "dropout", "label": "Dropout", "type": "float", "default": 0.1, "min": 0, "max": 0.5},
        {"name": "lr", "label": "学习率", "type": "float", "default": 0.0005, "min": 0.00001, "max": 0.01},
        {"name": "epochs", "label": "最大轮数", "type": "int", "default": 200, "min": 5, "max": 2000},
        {"name": "batch_size", "label": "批大小", "type": "int", "default": 128, "min": 8, "max": 2048},
        {"name": "patience", "label": "早停耐心", "type": "int", "default": 25, "min": 3, "max": 500},
    ]

    def build_module(self, n_in: int, n_out: int):
        d = int(self.params["d_token"])
        heads = int(self.params["n_heads"])
        if d % heads != 0:  # 保证可整除
            heads = max(h for h in (1, 2, 4, 8, 16) if d % h == 0 and h <= heads)
        return _build_ft_transformer(n_in, n_out, d, int(self.params["n_layers"]), heads, float(self.params["dropout"]))
