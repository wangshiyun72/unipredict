"""请求体数据结构（Pydantic），同时用于自动生成 OpenAPI 接口文档。"""
from __future__ import annotations

from typing import Any, Literal

import re

from pydantic import BaseModel, Field, field_validator

Visibility = Literal["private", "team", "public"]


class LoginIn(BaseModel):
    username: str
    password: str


EMAIL_PATTERN = r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"


class RegisterIn(BaseModel):
    username: str = Field(max_length=100, description="邮箱地址（作为登录账号，无需验证码）")
    password: str = Field(max_length=128, description="至少 6 位，不限字符类型")

    @field_validator("username")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if not re.match(EMAIL_PATTERN, v):
            raise ValueError("请输入正确的邮箱地址，例如 name@example.com")
        return v.lower()

    @field_validator("password")
    @classmethod
    def _pwd(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码至少 6 位")
        return v
    display_name: str | None = None
    team: str | None = Field(default="默认团队", max_length=50)


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


class KeyCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=50, description="用途说明，例如：实验室工作站脚本")
    rate_limit_per_min: int | None = Field(default=None, ge=1, le=1_000_000, description="仅管理员可自定义限额（压测脚本会用很大的值）")


class KeyPatchIn(BaseModel):
    is_active: bool | None = None
    rate_limit_per_min: int | None = Field(default=None, ge=1, le=1_000_000)


class TrainIn(BaseModel):
    dataset_id: int
    target: str = Field(description="目标列（要预测的列）")
    models: list[str] = Field(default_factory=list, description="模型 key 列表；为空时使用默认组合")
    task: Literal["regression", "classification"] | None = Field(default=None, description="为空时自动判断")
    params: dict[str, dict[str, Any]] = Field(default_factory=dict, description="各模型的参数 {模型key: {参数: 值}}")
    scaler: Literal["auto", "standard", "minmax", "robust", "none"] = "auto"
    test_size: float = Field(default=0.2, ge=0.05, le=0.5)
    drop_columns: list[str] = Field(default_factory=list, description="不参与训练的列")
    auto_publish: bool = Field(default=True, description="训练完成后自动发布最优模型")


class PredictIn(BaseModel):
    records: list[dict[str, Any]] = Field(min_length=1, description="待预测样本，每条是 {字段名: 值}")
    explain: bool = Field(default=False, description="是否返回局部可解释性（最多前 5 条）")

    model_config = {
        "json_schema_extra": {
            "examples": [{"records": [{"反应温度": 85, "反应时间": 6, "催化剂用量": 5, "底物摩尔比": 1.5,
                                       "溶剂": "DMF", "碱": "Cs2CO3"}], "explain": True}]
        }
    }


class PredictDatasetIn(BaseModel):
    dataset_id: int


class ModelPatchIn(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    status: Literal["ready", "published", "archived"] | None = None
    visibility: Visibility | None = None
    description: str | None = Field(default=None, max_length=1000)


class DatasetPatchIn(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    visibility: Visibility | None = None
    description: str | None = Field(default=None, max_length=1000)


class UserPatchIn(BaseModel):
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None
    team: str | None = Field(default=None, max_length=50)
    display_name: str | None = None
    rate_limit_per_min: int | None = Field(default=None, ge=1, le=100000)


class TemplateTrainIn(BaseModel):
    models: list[str] = Field(default_factory=list)
    target: str | None = None
