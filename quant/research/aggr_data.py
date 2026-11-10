"""激进版候选的数据：2 倍杠杆合成序列（ETF 上市前补齐用）与跟踪误差核对。"""
import pandas as pd

LEV_FEE = 0.0095  # SSO/QLD 费率
LEV_EXTRA = 0.007  # 2006-06～2026-09 真实 SSO/QLD 比合成序列每年少约 0.7%（互换成本等），合成段额外扣减，避免早年回测偏乐观
SYNTH_FEE = LEV_FEE + LEV_EXTRA


def leveraged(base: pd.Series, k: float, fee: float, rf_daily: pd.Series) -> pd.Series:
    """每日复利的 k 倍序列：日收益 = k×基础日收益 − 费率/252 − (k−1)×无风险日利率（借贷成本）；起点为 1。"""
    r = base.dropna().pct_change().fillna(0.0)
    rf = rf_daily.reindex(r.index).ffill().fillna(0.0)
    lr = k * r - fee / 252 - (k - 1) * rf
    lr.iloc[0] = 0.0
    return (1 + lr).cumprod()


def tracking_error(real: pd.Series, synth: pd.Series) -> float:
    """重叠期年化收益差（真实 − 合成）。"""
    df = pd.DataFrame({"r": real, "s": synth}).dropna()
    yrs = (len(df) - 1) / 252
    g = lambda x: (x.iloc[-1] / x.iloc[0]) ** (1 / yrs) - 1  # noqa: E731
    return g(df.r) - g(df.s)
