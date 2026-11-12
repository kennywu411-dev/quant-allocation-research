"""已登记的周线因子（定义与 spec.W_FACTORS 逐字一致；算式从 weekly.factors 原样搬来，回归测试保证数字不变）。
导入本模块即完成登记。新增因子：先在 spec.py 追加预先登记并提交，再在这里写函数。"""
import numpy as np

from quant.alpha import spec
from quant.alpha.registry import register

D = spec.W_FACTORS


@register("LOWVOL", D["LOWVOL"])
def lowvol(c):
    return c.at_rb(-c.ret.rolling(52, min_periods=26).std())


@register("MOM12_1", D["MOM12_1"])
def mom12_1(c):
    L = c.lg.cumsum().reindex(c.rb)
    return np.exp(L.shift(1) - L.shift(12)) - 1  # 第 t-11 到 t-1 个调仓月


@register("LOWTURN", D["LOWTURN"])
def lowturn(c):
    return c.at_rb(-c.w["turn"].where(c.w["traded"]).rolling(4, min_periods=2).mean())


@register("REV21", D["REV21"])
def rev21(c):
    return c.at_rb(-c.cum(4))


@register("SIZE", D["SIZE"])
def size(c):
    return c.at_rb(-np.log(c.mcap))


@register("IVOL", D["IVOL"])
def ivol(c):
    var_m = c.mkt.rolling(12, min_periods=8).var()
    cov = c.ret.rolling(12, min_periods=8).cov(c.mkt)
    var_r = c.ret.rolling(12, min_periods=8).var()
    resid = (var_r - cov.pow(2).div(var_m, axis=0)).clip(lower=0)
    return c.at_rb(-np.sqrt(resid))


@register("ILLIQ", D["ILLIQ"])
def illiq(c):
    amt = c.w["amount"].where(c.w["amount"] > 0)
    x = (c.ret.abs() / amt).rolling(4, min_periods=2).mean()
    return c.at_rb(np.log(x.where(x > 0)))


@register("REV5", D["REV5"])
def rev5(c):
    return c.at_rb(-c.r0)


@register("REV10", D["REV10"])
def rev10(c):
    return c.at_rb(-c.cum(2))


@register("MAX", D["MAX"])
def max_(c):
    return c.at_rb(-c.ret.rolling(4, min_periods=2).max())
