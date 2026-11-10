"""净值风险指标。回撤口径：从历史最高点到之后最低点，负数表示。"""
import numpy as np
import pandas as pd


def drawdown(nav: pd.Series) -> pd.Series:
    return nav / nav.cummax() - 1


def max_drawdown(nav: pd.Series) -> float:
    return float(drawdown(nav).min())


def current_drawdown(nav: pd.Series) -> float:
    return float(drawdown(nav).iloc[-1])


def cagr(nav: pd.Series) -> float:
    years = (nav.index[-1] - nav.index[0]).days / 365.25
    return float((nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1)


def ann_vol(nav: pd.Series) -> float:
    return float(nav.pct_change().dropna().std() * np.sqrt(252))


def sharpe(nav: pd.Series, rf: pd.Series) -> float:
    """年化夏普：日超额收益（净值收益减无风险资产收益，rf 为无风险资产的价格/指数序列）的均值 / 标准差 × √252。"""
    df = pd.DataFrame({"r": nav.pct_change(), "f": rf.reindex(nav.index).ffill().pct_change()}).dropna()
    ex = df.r - df.f
    return float(ex.mean() / ex.std() * np.sqrt(252))


def calmar(nav: pd.Series) -> float:
    """卡玛比率：年化收益 / |最大回撤|；从未回撤时为无穷大。"""
    mdd = max_drawdown(nav)
    return cagr(nav) / abs(mdd) if mdd < 0 else float("inf")


def worst_drawdowns(nav: pd.Series, n: int = 5) -> pd.DataFrame:
    dd = drawdown(nav)
    rows = []
    in_dd = False
    for date, v in dd.items():
        if v < 0 and not in_dd:
            in_dd = True
            peak = dd.index[dd.index.get_loc(date) - 1]
        elif v == 0 and in_dd:
            seg = dd.loc[peak:date]
            rows.append((peak, seg.idxmin(), date, float(seg.min())))
            in_dd = False
    if in_dd:
        seg = dd.loc[peak:]
        rows.append((peak, seg.idxmin(), pd.NaT, float(seg.min())))
    df = pd.DataFrame(rows, columns=["peak", "trough", "recovery", "depth"])
    return df.sort_values("depth").head(n).reset_index(drop=True)
