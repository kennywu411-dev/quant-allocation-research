"""组合模拟（涨跌停约束、成本）、因子合成（等权 / IC 加权 / LightGBM）与汇总指标。"""
import numpy as np
import pandas as pd

from quant.alpha import spec
from quant.factors import evaluate as fev


def zscores(f: pd.DataFrame, univ: pd.DataFrame) -> pd.DataFrame:
    """每个月在股票池内缩尾 + 标准化；池外为 NaN。"""
    out = pd.DataFrame(np.nan, index=f.index, columns=f.columns)
    for t in f.index:
        m = univ.loc[t]
        z = fev.preprocess(f.loc[t, m[m].index])
        out.loc[t, z.index] = z
    return out


def quantile_sets(f: pd.DataFrame, univ: pd.DataFrame, n: int = spec.N_GROUPS) -> dict:
    """{月末: (最低组集合, 最高组集合)}；只用池内、因子不缺的股票。"""
    out = {}
    for t in f.index:
        m = univ.loc[t]
        x = f.loc[t, m[m].index].dropna()
        if len(x) < n * 20:
            continue
        r = x.rank(method="first", pct=True)
        out[t] = (set(r[r <= 1 / n].index), set(r[r > 1 - 1 / n].index))
    return out


def simulate(target: dict, fwd: pd.DataFrame, up: pd.DataFrame, dn: pd.DataFrame, tradable: pd.DataFrame) -> pd.DataFrame:
    """等权月度调仓的纯多头组合：t 日收盘涨停的不能新买；跌停或停牌的已持仓卖不出、留到下月。
    返回持有月份（t+1 月末）索引的 毛收益、单边换手、净收益。"""
    held, rows = set(), {}
    for t in sorted(target):
        want = target[t]
        buy_ok = {c for c in want - held if not bool(up.at[t, c])} if len(want - held) else set()
        stuck = {c for c in held - want if bool(dn.at[t, c]) or not bool(tradable.at[t, c])}
        new = (want & held) | buy_ok | stuck
        if not new:
            continue
        turn = 1.0 if not held else len(new - held) / len(new)
        r = fwd.loc[t, list(new)].fillna(0.0).mean()
        nxt = t + pd.offsets.MonthEnd(1)
        rows[nxt] = {"gross": float(r), "turn": turn, "net": float(r) - turn * fev.cost_rate(nxt), "n": len(new)}
        held = new
    return pd.DataFrame(rows).T.sort_index()


def max_drawdown(r: pd.Series) -> float:
    nav = (1 + r.fillna(0)).cumprod()
    return float((nav / nav.cummax() - 1).min())


def ic_weighted(z: dict[str, pd.DataFrame], ic: dict[str, pd.Series], window: int = spec.IC_WINDOW) -> pd.DataFrame:
    """IC 加权：月末 t 的权重 = max(过去 window 个月已实现 RankIC 均值, 0)；t 月的 IC 要到 t+1 月末才知道，所以用到 t-1。"""
    names = list(z)
    icdf = pd.DataFrame(ic).reindex(z[names[0]].index)
    w = icdf.shift(1).rolling(window, min_periods=12).mean().clip(lower=0)
    w = w.div(w.sum(axis=1).replace(0, np.nan), axis=0)
    out = sum(z[k].mul(w[k], axis=0).fillna(0) * z[k].notna() for k in names)
    has = sum(z[k].notna().astype(float) for k in names)
    return out.where((has > 0) & w.notna().any(axis=1).to_numpy()[:, None])


def equal_weighted(z: dict[str, pd.DataFrame]) -> pd.DataFrame:
    stack = np.stack([z[k].to_numpy(dtype=float) for k in z])
    with np.errstate(all="ignore"):
        m = np.nanmean(stack, axis=0)
    return pd.DataFrame(m, index=z[next(iter(z))].index, columns=z[next(iter(z))].columns)


def lgb_composite(f: dict[str, pd.DataFrame], fwd: pd.DataFrame, univ: pd.DataFrame) -> pd.DataFrame:
    """LightGBM：特征 = 各因子截面分位数，目标 = 下月收益截面分位数。每年 12 月末重训，只用标签已实现的月份
    （月末 m 的标签在 m+1 月末才知道，所以训练集截到上一个月末），窗口 spec.LGB_TRAIN_MONTHS 个月，至少 24 个月。"""
    import lightgbm as lgb
    names = list(f)
    idx = univ.index
    feat = {k: f[k].where(univ).rank(axis=1, pct=True) for k in names}
    tgt = fwd.where(univ).rank(axis=1, pct=True)

    def rows(months):
        X = np.column_stack([feat[k].loc[months].stack(future_stack=True).to_numpy() for k in names])
        y = tgt.loc[months].stack(future_stack=True).to_numpy()
        keep = ~np.isnan(y) & (np.isnan(X).sum(axis=1) < len(names) // 2)
        return X[keep], y[keep]

    pred = pd.DataFrame(np.nan, index=idx, columns=univ.columns)
    decembers = [t for t in idx if t.month == 12]
    for k, t in enumerate(decembers):
        pos = idx.get_loc(t)
        train = idx[max(0, pos - spec.LGB_TRAIN_MONTHS):pos]  # 截到 t 的上一个月末：其标签在 t 已实现
        if len(train) < 24:
            continue
        X, y = rows(train)
        model = lgb.LGBMRegressor(**spec.LGB_PARAMS)
        model.fit(X, y)
        end = decembers[k + 1] if k + 1 < len(decembers) else idx[-1] + pd.offsets.MonthEnd(1)
        for m in idx[(idx >= t) & (idx < end)]:
            ok = univ.loc[m]
            Xm = np.column_stack([feat[n].loc[m, ok[ok].index].to_numpy() for n in names])
            pred.loc[m, ok[ok].index] = model.predict(Xm)
    return pred


def summarize(f: pd.DataFrame, fwd: pd.DataFrame, univ: pd.DataFrame, up: pd.DataFrame, dn: pd.DataFrame,
              tradable: pd.DataFrame) -> dict:
    """单个因子或合成的全部指标。"""
    ic = fev.ic_series(f, fwd, univ)
    full, ins, oos = fev.ic_summary(ic), fev.ic_summary(ic[ic.index <= spec.SPLIT]), fev.ic_summary(ic[ic.index > spec.SPLIT])
    sets = quantile_sets(f, univ)
    top = simulate({t: s[1] for t, s in sets.items()}, fwd, up, dn, tradable)
    bot = simulate({t: s[0] for t, s in sets.items()}, fwd, up, dn, tradable)
    bench = pd.Series({t + pd.offsets.MonthEnd(1): float(fwd.loc[t, univ.loc[t]].fillna(0).mean()) for t in sets})
    ex = (top.net - bench.reindex(top.index)).dropna()
    ls = (top.net - bot.gross.reindex(top.index)).dropna()  # 空头腿只作参考，不扣融券成本
    o = lambda s: s[s.index > pd.Timestamp(spec.SPLIT) + pd.offsets.MonthEnd(1)]
    ann = fev.ann_return
    res = {"ic": ic, "excess": ex, "ls": ls,
           "summary": {"rank_ic": full["mean"], "t": full["t"], "icir_ann": full["icir_ann"], "n": full["n"],
                       "is_rank_ic": ins["mean"], "is_t": ins["t"], "oos_rank_ic": oos["mean"], "oos_t": oos["t"],
                       "oos_icir_ann": oos["icir_ann"],
                       "ex_ann": ann(ex), "oos_ex_ann": ann(o(ex)), "ex_mdd": max_drawdown(ex), "oos_ex_mdd": max_drawdown(o(ex)),
                       "ls_ann": ann(ls), "oos_ls_ann": ann(o(ls)), "oos_ls_mdd": max_drawdown(o(ls)),
                       "top_turn": float(top.turn.iloc[1:].mean()), "top_ann_net": ann(top.net)}}
    s = res["summary"]
    s["passed"] = bool(s["t"] >= spec.T_PASS and s["oos_rank_ic"] > 0 and s["oos_ex_ann"] > 0)
    return res
