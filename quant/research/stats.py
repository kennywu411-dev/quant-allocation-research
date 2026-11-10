"""卫星因子的统计检验：alpha t 值（Newey-West）和通缩夏普比率（Bailey & López de Prado 2014）。"""
import math
from statistics import NormalDist

import numpy as np
import pandas as pd

_N = NormalDist()
EULER = 0.5772156649


def monthly_returns(nav: pd.Series) -> pd.Series:
    return nav.resample("ME").last().pct_change().dropna()


def alpha_t(asset: pd.Series, bench: pd.Series, lags: int = 3, rf: pd.Series | None = None) -> dict:
    """月收益回归 r_a - rf = α + β (r_b - rf)，α 的 t 值用 Newey-West 标准误。
    不减 rf 时 α 会混入 (1-β)·rf，低 beta 资产的 α 被高估。"""
    df = pd.DataFrame({"a": asset, "b": bench}).dropna()
    if rf is not None:
        df = df.join(rf.rename("rf"), how="inner").dropna()
        df = pd.DataFrame({"a": df.a - df.rf, "b": df.b - df.rf})
    y, X = df.a.to_numpy(), np.column_stack([np.ones(len(df)), df.b.to_numpy()])
    xtx_inv = np.linalg.inv(X.T @ X)
    coef = xtx_inv @ X.T @ y
    u = y - X @ coef
    xu = X * u[:, None]
    S = xu.T @ xu
    for L in range(1, lags + 1):
        w = 1 - L / (lags + 1)
        G = xu[L:].T @ xu[:-L]
        S += w * (G + G.T)
    se = np.sqrt(np.diag(xtx_inv @ S @ xtx_inv))
    return {"alpha_ann": (1 + coef[0]) ** 12 - 1, "beta": float(coef[1]),
            "t_alpha": float(coef[0] / se[0]), "n_months": len(df)}


def deflated_sharpe(returns: pd.Series, n_trials: int, sr_trials_var: float) -> float:
    """收益序列的夏普（非年化）超过 n_trials 次试验期望最大夏普的概率。n_trials ≤ 1 时退化为 PSR（基准 0）。"""
    x = returns.dropna().to_numpy()
    T = len(x)
    sr = x.mean() / x.std(ddof=1)
    sd0 = x.std(ddof=0)
    skew = ((x - x.mean()) ** 3).mean() / sd0 ** 3
    kurt = ((x - x.mean()) ** 4).mean() / sd0 ** 4
    if n_trials <= 1:
        sr0 = 0.0
    else:
        sr0 = math.sqrt(sr_trials_var) * ((1 - EULER) * _N.inv_cdf(1 - 1 / n_trials)
                                          + EULER * _N.inv_cdf(1 - 1 / (n_trials * math.e)))
    return _N.cdf((sr - sr0) * math.sqrt(T - 1) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr ** 2))
