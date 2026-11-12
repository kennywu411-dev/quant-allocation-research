"""因子注册表：写一个函数、加一行 @register，就能被体检报告、月度流水线和看板按名字使用。

    @register("NAME", "定义（方向统一为值越大、预期下月收益越高）")
    def name(ctx):            # ctx.w = 周线面板，ctx.rb = 调仓日；常用中间量在 Ctx 上按需计算并缓存
        return ...            # 调仓日 × 股票 的 DataFrame

纪律：登记进注册表只代表“能算”；要对真实数据出结果，名字必须先写进 spec.py 的预先登记并提交（见 preregistered）。"""
from dataclasses import dataclass
from functools import cached_property
from typing import Callable

import numpy as np
import pandas as pd

from quant.alpha import spec


@dataclass(frozen=True)
class Factor:
    name: str
    desc: str
    fn: Callable
    source: str = "价量（baostock 周线）"


REGISTRY: dict[str, Factor] = {}
PREREGISTERED_COMPOSITES = [*spec.COMPOSITES, "慢因子合成"]


def register(name: str, desc: str, source: str = "价量（baostock 周线）", registry: dict | None = None):
    reg = REGISTRY if registry is None else registry

    def deco(fn):
        if name in reg:
            raise ValueError(f"因子 {name} 已登记，不能重名")
        reg[name] = Factor(name, desc, fn, source)
        return fn
    return deco


def preregistered(name: str) -> bool:
    """名字是否在 spec.py 的预先登记名单里（单因子或合成）。"""
    return name in spec.W_FACTORS or name in PREREGISTERED_COMPOSITES


class Ctx:
    """因子函数的输入：周线面板 w、调仓日 rb，以及多个因子共用的中间量（只算一次）。"""

    def __init__(self, w: dict, rb: pd.DatetimeIndex):
        self.w, self.rb = w, rb

    @cached_property
    def ret(self):
        return self.w["ret"]

    @cached_property
    def r0(self):
        return self.ret.fillna(0.0)

    @cached_property
    def lg(self):
        return np.log1p(self.r0)

    def cum(self, n: int) -> pd.DataFrame:
        """过去 n 周累计收益。"""
        return np.exp(self.lg.rolling(n).sum()) - 1

    @cached_property
    def mkt(self):
        return self.ret.mean(axis=1)

    @cached_property
    def mcap(self):
        """流通市值 = 周成交额 / 周换手率；换手为 0 的周沿用之前的值（最多 4 周）。"""
        w = self.w
        return (w["amount"] / (w["turn"].where(w["turn"] > 0) / 100)).ffill(limit=4)

    def at_rb(self, x: pd.DataFrame) -> pd.DataFrame:
        return x.reindex(self.rb)


def compute(names, ctx: Ctx, registry: dict | None = None) -> dict[str, pd.DataFrame]:
    reg = REGISTRY if registry is None else registry
    return {k: reg[k].fn(ctx) for k in names}
