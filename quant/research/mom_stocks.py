"""美股动量个股落地检验：python -m quant.research.mom_stocks
股票池是“今天的”纳指100 + 标普100 成分股，所以回测有幸存者偏差（只包含活到今天且变大的公司）；
和同期 French 大盘高动量组合（含退市股）对比，差额视为幸存者偏差与实现差距的上界估计。"""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

UNIVERSE = Path("config/mom_universe.csv")
START = "2015-01-01"
N = 15
DISCLAIMER = "> 声明：本报告不是投资建议，回测结果不代表未来收益。作者不是持牌金融顾问。"


def momentum_rank(px: pd.DataFrame, asof: pd.Timestamp, lookback: int = 252, skip: int = 21) -> pd.Series:
    """12-1 动量：t−lookback 到 t−skip 的涨幅，降序；数据不足的股票不参与。"""
    hist = px.loc[:asof]
    if len(hist) <= lookback:
        return pd.Series(dtype=float)
    p0, p1 = hist.iloc[-lookback - 1], hist.iloc[-skip - 1]
    m = (p1 / p0 - 1).dropna()
    return m.sort_values(ascending=False)


def top_n_portfolio(px: pd.DataFrame, n: int, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """每个调仓日等权持有动量前 n 名。"""
    rows = []
    for d in dates:
        r = momentum_rank(px, d)
        if len(r) < n:
            continue
        w = pd.Series(0.0, index=px.columns)
        w[r.index[:n]] = 1.0 / n
        rows.append(w.rename(d))
    return pd.DataFrame(rows)


def _cagr(s: pd.Series) -> float:
    s = s.dropna()
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / (len(s) - 1)) - 1)


def bias_report(real_nav: pd.Series, french_nav: pd.Series) -> dict:
    df = pd.DataFrame({"r": real_nav, "f": french_nav}).dropna()
    mdd = lambda s: float((s / s.cummax() - 1).min())  # noqa: E731
    return {"real_cagr": _cagr(df.r), "french_cagr": _cagr(df.f), "bias": _cagr(df.r) - _cagr(df.f),
            "real_mdd": mdd(df.r), "french_mdd": mdd(df.f), "start": df.index[0], "end": df.index[-1]}


def load_prices(get_price) -> tuple[pd.DataFrame, list[str]]:
    syms = pd.read_csv(UNIVERSE).symbol.tolist()
    series, failed = {}, []
    for s in syms:
        try:
            series[s] = get_price(s, "US", "stock")
        except Exception:
            failed.append(s)
    return pd.DataFrame(series).sort_index().loc["2013-01-01":], failed


def current_picks(px: pd.DataFrame, n: int = N, asof: pd.Timestamp | None = None) -> list[str]:
    from quant.portfolio.transition import last_complete_month_end
    asof = asof or last_complete_month_end(px.index, pd.Timestamp.today())[-1]
    return list(momentum_rank(px, asof).index[:n])


def main() -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from quant.backtest import costs
    from quant.backtest.engine import run_backtest
    from quant.backtest.strategies import rebalance_dates
    from quant.data.update import get_french, get_price

    px, failed = load_prices(get_price)
    dates = rebalance_dates(px.loc[START:], "end")
    w = top_n_portfolio(px, N, dates)
    res = run_backtest(px.loc[w.index[0]:], w, {s: costs.us_stock() for s in px}, 10_000.0, fractional=True)
    french = get_french("6_Portfolios_ME_Prior_12_2_daily", "BIG HiPRIOR")
    end = min(res.nav.index[-1], french.index[-1])
    b = bias_report(res.nav.loc[:end], french.loc[res.nav.index[0]:end])
    spy = get_price("SPY", "US", "etf").loc[b["start"]:end]
    qqq = get_price("QQQ", "US", "etf").loc[b["start"]:end]
    turnover = float(w.diff().abs().sum(axis=1).iloc[1:].mean() / 2)
    out = [f"# 美股动量个股落地检验（{date.today()}）", "",
           f"股票池：今天的纳指100 + 标普100 成分股，共 {px.shape[1]} 只（取名单日期见 `config/mom_universe.csv`）；"
           f"每月末按 12-1 动量等权持有前 {N} 名，碎股，成本按 moomoo 美股个股（每单 0.99 美元 + 0.1% 滑点）。", "",
           f"区间 {b['start']:%Y-%m-%d} 至 {b['end']:%Y-%m-%d}（美元计）：", "",
           "| | 年化 | 最大回撤 |", "|---|---|---|",
           f"| 真实个股前 {N} 名 | {b['real_cagr'] * 100:.1f}% | {b['real_mdd'] * 100:.0f}% |",
           f"| French 大盘高动量组合（含退市股） | {b['french_cagr'] * 100:.1f}% | {b['french_mdd'] * 100:.0f}% |",
           f"| SPY | {_cagr(spy) * 100:.1f}% | {float((spy / spy.cummax() - 1).min()) * 100:.0f}% |",
           f"| QQQ | {_cagr(qqq) * 100:.1f}% | {float((qqq / qqq.cummax() - 1).min()) * 100:.0f}% |", "",
           f"**真实个股组合比 French 组合每年高 {b['bias'] * 100:.1f} 个百分点**：这部分主要来自幸存者偏差"
           "（今天的成分股都是活下来并变大的公司）和集中度（15 只 vs 数百只），不能当作可重复的超额收益。"
           "激进版回测里的“大盘动量个股组合”用的是 French 序列，不含这部分偏差。", "",
           f"平均每月单边换手约 {turnover * 100:.0f}%。按年化计，频繁换手会让持有不满 12 个月的盈利拿不到澳洲资本利得税 50% 折扣。", "",
           *([f"取数失败、未纳入：{'、'.join(failed)}", ""] if failed else []), DISCLAIMER, ""]
    import json
    Path("research/mom_bias.json").write_text(json.dumps(
        {k: (f"{v:%Y-%m-%d}" if isinstance(v, pd.Timestamp) else v) for k, v in b.items()} | {"turnover": turnover},
        ensure_ascii=False, indent=1))
    path = Path("reports") / f"动量个股检验-{date.today()}.md"
    path.write_text("\n".join(out))
    print("已生成：", path, b, "换手", turnover)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
