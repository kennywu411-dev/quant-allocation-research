"""单因子检验指标：截面预处理、IC / RankIC、五分组收益与多空、换手与成本、分样本与分年度。
判定标准（运行前固定）：全期 RankIC 均值的 t 值 ≥ 3（7 个因子同时检验，按 Harvey, Liu & Zhu 2016 的多重检验门槛），
且样本外（2020 年起）RankIC 均值与全期同号，才算“显著”；t 在 2 到 3 之间记为“弱”。"""
import numpy as np
import pandas as pd

SPLIT = "2019-12-31"
T_SIG, T_WEAK = 3.0, 2.0
N_GROUPS = 5
STAMP_CUT = pd.Timestamp("2023-08-28")  # 印花税减半日


def preprocess(x: pd.Series, lo: float = 0.01, hi: float = 0.99) -> pd.Series:
    """截面 1%/99% 缩尾后标准化。"""
    x = x.dropna()
    if len(x) < 3:
        return x * np.nan
    x = x.clip(x.quantile(lo), x.quantile(hi))
    sd = x.std()
    return (x - x.mean()) / sd if sd > 0 else x * np.nan


def ic_series(factor: pd.DataFrame, fwd: pd.DataFrame, mask: pd.DataFrame, rank: bool = True,
              min_n: int = 30) -> pd.Series:
    """每个月末：因子值（预处理后）与下月收益的截面相关；rank=True 为 Spearman（RankIC）。"""
    out = {}
    for t in factor.index:
        if t not in mask.index or t not in fwd.index:
            continue
        m = mask.loc[t]
        f = preprocess(factor.loc[t, m[m].index])
        r = fwd.loc[t, f.index]
        ok = f.notna() & r.notna()
        if ok.sum() < min_n:
            continue
        out[t] = f[ok].corr(r[ok], method="spearman" if rank else "pearson")
    return pd.Series(out, dtype=float)


def ic_summary(ic: pd.Series) -> dict:
    ic = ic.dropna()
    n, mu, sd = len(ic), float(ic.mean()), float(ic.std())
    return {"n": n, "mean": mu, "std": sd, "icir": mu / sd, "icir_ann": mu / sd * np.sqrt(12),
            "t": mu / sd * np.sqrt(n), "win": float((ic > 0).mean())}


def verdict(full: dict, oos: dict) -> str:
    if full["t"] >= T_SIG and np.sign(oos["mean"]) == np.sign(full["mean"]):
        return "显著"
    if full["t"] >= T_WEAK and np.sign(oos["mean"]) == np.sign(full["mean"]):
        return "弱"
    if full["t"] <= -T_WEAK:
        return "方向相反"
    return "不显著"


def groups(factor: pd.DataFrame, mask: pd.DataFrame, fwd: pd.DataFrame, n: int = N_GROUPS) -> dict:
    """每个月末按因子值等分 n 组（1 = 最低，n = 最高），只用下月收益不为空的股票。返回 {月末: {组号: 股票列表}}。"""
    out = {}
    for t in factor.index:
        if t not in mask.index or t not in fwd.index:
            continue
        m = mask.loc[t]
        f = factor.loc[t, m[m].index].dropna()
        f = f[fwd.loc[t, f.index].notna()]
        if len(f) < n * 5:
            continue
        q = pd.qcut(f.rank(method="first"), n, labels=range(1, n + 1))
        out[t] = {g: list(q[q == g].index) for g in range(1, n + 1)}
    return out


def hold_label(t: pd.Timestamp) -> pd.Timestamp:
    """月末 t 建仓的持有期标签 = 下一个自然月的月末。
    不能写 t + MonthEnd(1)：t 不在自然月末时它落回当月月末，会和上一期（恰在自然月末建仓）的标签重复，后一期覆盖前一期。"""
    return (pd.Timestamp(t).to_period("M") + 1).end_time.normalize()


def group_returns(grp: dict, fwd: pd.DataFrame) -> pd.DataFrame:
    """各组等权下月收益；索引为持有月份的月末（t+1）。"""
    rows = {}
    for t, gs in grp.items():
        rows[hold_label(t)] = {g: float(fwd.loc[t, codes].mean()) for g, codes in gs.items()}
    return pd.DataFrame(rows).T.sort_index()


def turnover(grp: dict, g: int) -> pd.Series:
    """某组每月单边换手（等权）：新持仓里上月没有的股票占比；第一个月记 1（建仓）。"""
    out, prev = {}, None
    for t in sorted(grp):
        cur = set(grp[t][g])
        out[hold_label(t)] = 1.0 if prev is None else len(cur - prev) / len(cur)
        prev = cur
    return pd.Series(out)


def cost_rate(t: pd.Timestamp) -> float:
    """每单位单边换手的往返成本：买卖各一次佣金 0.025% + 滑点 0.1%，卖出印花税 2023-08-28 前 0.1%、之后 0.05%（与 costs.cn_stock 一致）。"""
    stamp = 0.001 if t < STAMP_CUT else 0.0005
    return 2 * (0.00025 + 0.001) + stamp


def ann_return(r: pd.Series) -> float:
    r = r.dropna()
    return float((1 + r).prod() ** (12 / len(r)) - 1) if len(r) else float("nan")


def long_short(gr: pd.DataFrame, grp: dict, n: int = N_GROUPS) -> pd.DataFrame:
    """多空（最高组 - 最低组）和多头超额（最高组 - 股票池等权），各给扣成本前后。"""
    top_to, bot_to = turnover(grp, n), turnover(grp, 1)
    cost = pd.Series([cost_rate(t) for t in gr.index], index=gr.index)
    univ = gr.mean(axis=1)  # 各组等权平均 ≈ 股票池等权
    return pd.DataFrame({
        "ls": gr[n] - gr[1], "ls_net": gr[n] - gr[1] - (top_to + bot_to).reindex(gr.index) * cost,
        "top_ex": gr[n] - univ, "top_ex_net": gr[n] - univ - top_to.reindex(gr.index) * cost,
        "top_turn": top_to.reindex(gr.index), "bot_turn": bot_to.reindex(gr.index)})


def by_year(ic: pd.Series, ls: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"rank_ic": ic.groupby(ic.index.year).mean(),
                         "ls": ls.groupby(ls.index.year).apply(lambda r: float((1 + r).prod() - 1))})
