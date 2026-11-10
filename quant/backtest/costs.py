"""交易成本模型。取值见 docs/系统设计.md 第 4 节。"""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CostModel:
    commission_rate: float = 0.0
    min_commission: float = 0.0
    per_order: float = 0.0
    stamp_sell: float = 0.0
    slippage: float = 0.0
    lot: int = 1

    def cost(self, side: Literal["buy", "sell"], value: float) -> float:
        if value <= 0:
            return 0.0
        c = max(value * self.commission_rate, self.min_commission) + self.per_order + value * self.slippage
        if side == "sell":
            c += value * self.stamp_sell
        return c


def us_etf() -> CostModel:
    return CostModel(per_order=0.99, slippage=0.0005)


def us_stock() -> CostModel:
    return CostModel(per_order=0.99, slippage=0.001)


def cn_etf() -> CostModel:
    return CostModel(commission_rate=0.00025, min_commission=5.0, slippage=0.0005, lot=100)


def cn_stock() -> CostModel:
    return CostModel(commission_rate=0.00025, min_commission=5.0, stamp_sell=0.0005, slippage=0.001, lot=100)


def zero(lot: int = 1) -> CostModel:
    return CostModel(lot=lot)


def scaled(m: CostModel, k: float) -> CostModel:
    """所有成本项乘以 k（用于成本 ×2 压力测试），交易单位不变。"""
    return CostModel(m.commission_rate * k, m.min_commission * k, m.per_order * k, m.stamp_sell * k, m.slippage * k, m.lot)
