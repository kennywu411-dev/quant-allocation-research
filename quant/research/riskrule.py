"""P5 风控规则：合并回撤到 -15% 时降低股票仓位，并用平稳分块自助法比较规则。

两档仓位：核心（core_r）和股票清零的防守版（def_r）。规则在 t 日收盘按叠加后净值的回撤决定状态，t+1 日起生效。
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Rule:
    name: str
    cut: float      # 触发后从核心移到防守版的比例：0 / 0.5 / 1
    resume: str     # "dd"：回撤回到 resume_dd 以内恢复；"days"：触发满 resume_days 个交易日恢复


RULES = [Rule("无规则", 0.0, "dd"), Rule("减半-回升", 0.5, "dd"), Rule("减半-3月", 0.5, "days"),
         Rule("清零-回升", 1.0, "dd"), Rule("清零-3月", 1.0, "days")]


def overlay_np(core: np.ndarray, de: np.ndarray, rule: Rule, trigger: float = -0.15, resume_dd: float = -0.10,
               resume_days: int = 63, switch_cost: float = 0.002) -> tuple[np.ndarray, np.ndarray]:
    """core、de 形状 (路径数, 天数) 的日收益。返回净值 (路径数, 天数) 和每条路径的切换次数。"""
    P, T = core.shape
    nav = np.empty((P, T))
    level, peak = np.ones(P), np.ones(P)
    on = np.zeros(P, dtype=bool)
    since = np.zeros(P, dtype=int)
    switches = np.zeros(P, dtype=int)
    for t in range(T):
        w = np.where(on, rule.cut, 0.0)
        level = level * (1 + (1 - w) * core[:, t] + w * de[:, t])
        peak = np.maximum(peak, level)
        if rule.cut > 0:
            dd = level / peak - 1
            since = since + on
            go = ~on & (dd <= trigger)
            back = on & ((dd > resume_dd) if rule.resume == "dd" else (since >= resume_days))
            flip = go | back
            level = np.where(flip, level * (1 - switch_cost * rule.cut), level)
            on = on ^ flip
            since = np.where(go, 0, since)
            switches += flip
        nav[:, t] = level
    return nav, switches


def overlay(core_r: pd.Series, def_r: pd.Series, rule: Rule, **kw) -> tuple[pd.Series, int]:
    df = pd.DataFrame({"c": core_r, "d": def_r}).dropna()
    nav, n = overlay_np(df.c.to_numpy()[None, :], df.d.to_numpy()[None, :], rule, **kw)
    return pd.Series(nav[0], df.index), int(n[0])


def block_bootstrap(df: pd.DataFrame, n_paths: int, length: int, mean_block: int, seed: int) -> np.ndarray:
    """平稳分块自助法（Politis & Romano 1994）：块长服从均值 mean_block 的几何分布，块到末尾环绕；各列同一天成对抽取。"""
    rng = np.random.default_rng(seed)
    n = len(df)
    idx = np.empty((n_paths, length), dtype=int)
    idx[:, 0] = rng.integers(0, n, n_paths)
    for t in range(1, length):
        new = rng.random(n_paths) < 1 / mean_block
        idx[:, t] = np.where(new, rng.integers(0, n, n_paths), (idx[:, t - 1] + 1) % n)
    return df.to_numpy()[idx]


def _mdd(nav: np.ndarray) -> np.ndarray:
    return (nav / np.maximum.accumulate(nav, axis=1) - 1).min(axis=1)


def evaluate_rules(core_r: pd.Series, def_r: pd.Series, rules: list[Rule], n_paths: int, length: int,
                   mean_block: int, seed: int) -> pd.DataFrame:
    df = pd.DataFrame({"c": core_r, "d": def_r}).dropna()
    x = block_bootstrap(df, n_paths, length, mean_block, seed)
    rows = {}
    for rule in rules:
        nav, sw = overlay_np(x[:, :, 0], x[:, :, 1], rule)
        mdd, cg = _mdd(nav), nav[:, -1] ** (252 / length) - 1
        rows[rule.name] = {"p_breach20": float(np.mean(mdd < -0.20)), "p_breach15": float(np.mean(mdd < -0.15)),
                           "median_cagr": float(np.median(cg)), "p5_cagr": float(np.percentile(cg, 5)),
                           "median_mdd": float(np.median(mdd)), "p5_mdd": float(np.percentile(mdd, 5)),
                           "mean_switches": float(sw.mean()), "p_trigger": float(np.mean(sw > 0))}
    return pd.DataFrame(rows).T


def pick_rule(table: pd.DataFrame) -> str:
    """跌破 -20% 概率最低；与最低值相差不到 1 个百分点的规则里选中位年化最高。"""
    near = table[table.p_breach20 - table.p_breach20.min() < 0.01]
    return str(near.median_cagr.idxmax())
