"""持仓体检命令行：python -m quant.checkup"""
import argparse
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from quant.data.update import get_price, latest_quote, load_universe
from quant.fx import align, to_aud
from quant.metrics import current_drawdown, drawdown, max_drawdown, worst_drawdowns
from quant.portfolio.checkup import (cash_price_aud, current_values_aud, fill_with_proxy, portfolio_nav,
                                     risk_contribution, stress_table, weekly_returns, weighted_nav)
from quant.portfolio.holdings import load_holdings
from quant.report.checkup_report import render


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdings", default="config/holdings.csv")
    ap.add_argument("--proxies", default="config/proxies.csv")
    ap.add_argument("--out", default="reports")
    a = ap.parse_args(argv)

    h = load_holdings(Path(a.holdings))
    if h["shares"].isna().any():
        missing = ", ".join(h.loc[h["shares"].isna(), "symbol"])
        print(f"请填写股数（或现金金额）：{missing}，文件 {a.holdings}")
        return 2

    uni = load_universe().set_index("symbol")
    proxies = pd.read_csv(a.proxies, dtype=str).set_index("symbol") if Path(a.proxies).exists() else pd.DataFrame()
    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    fx_last = {"USD": float(fx["AUDUSD"].iloc[-1]), "CNY": float(fx["AUDCNY"].iloc[-1]), "AUD": 1.0}

    stocks = h[h.symbol != "CASH"]
    last, series, notes, srcs, asset_rows, info = {}, {}, [], {}, {}, {}
    real_since = None

    def _info(name, s):
        info[name] = {"最后日期": s.index[-1].date(), "来源": s.attrs.get("source", ""),
                      "抓取时间": s.attrs.get("fetched_at", ""), "旧缓存": bool(s.attrs.get("stale", False))}

    for k, s in fx.items():
        _info(k, s)
    for r in stocks.itertuples():
        kind = uni.loc[r.symbol, "kind"] if r.symbol in uni.index else "stock"
        adj = get_price(r.symbol, r.market, kind)
        _info(r.symbol, adj)
        srcs[r.symbol] = adj.attrs.get("source", "")
        qd, qp = latest_quote(r.symbol, r.market, kind)
        last[r.symbol] = qp
        adj = adj * qp / adj.asof(qd)  # 在同一日期对齐后缩放到实际价
        asset_rows[r.symbol] = {"start": adj.index[0].date(), "max_dd": max_drawdown(adj), "cur_dd": current_drawdown(adj)}
        if r.symbol in proxies.index:
            p = proxies.loc[r.symbol]
            filled, cut = fill_with_proxy(adj, get_price(p.proxy, "US", "etf"), vol_scale=True)
            if cut is not None:
                notes.append(f"{r.symbol}：{cut:%Y-%m-%d} 之前没有价格，用 {p.proxy} 的收益补齐，并按 {r.symbol} 上市后的"
                             f"真实波动放大（{p.note}）。这部分回放可信度低。")
                adj = filled
                real_since = max(real_since or cut, cut)
        series[r.symbol] = to_aud(adj, r.ccy, fx)

    values = current_values_aud(h, last, fx_last)
    for ccy in h.loc[h.symbol == "CASH", "ccy"].unique():
        idx = fx["AUDUSD"].index.union(fx["AUDCNY"].index)
        series[f"CASH_{ccy}"] = cash_price_aud(ccy, fx, idx)

    prices_aud = align(series).dropna()
    weights = values / values.sum()
    nav = weighted_nav(weights, prices_aud)

    h_aud = h.copy()
    cash = h_aud.symbol == "CASH"
    h_aud.loc[cash, "shares"] = h_aud.loc[cash].apply(lambda r: r.shares / fx_last[r.ccy], axis=1)
    h_aud.loc[cash, "ccy"] = "AUD"
    nav_ref = portfolio_nav(h_aud, prices_aud[[c for c in prices_aud if not c.startswith("CASH_")]])

    wk = weekly_returns(prices_aud)
    rc = risk_contribution(weights, wk)
    rc_real = risk_contribution(weights, weekly_returns(prices_aud.loc[real_since:])) if real_since is not None else None
    stock_cols = [c for c in wk if not c.startswith("CASH_")]
    estimates = [f"{r.symbol}（{r.ccy}）：{r.note}" for r in h.itertuples() if "估算" in str(r.note)]
    as_of = date.today()
    md = render(h, nav, values, rc, wk[stock_cols].corr(), stress_table(nav), worst_drawdowns(nav), notes, as_of,
                asset_dd=pd.DataFrame(asset_rows).T, sources=srcs, nav_ref=nav_ref, estimates=estimates,
                data_info=pd.DataFrame(info).T, rc_real=rc_real,
                real_since=None if real_since is None else f"{real_since:%Y-%m-%d}")

    out = Path(a.out)
    out.mkdir(exist_ok=True)
    md_path, png_path = out / f"持仓体检-{as_of}.md", out / f"持仓体检-{as_of}.png"
    md_path.write_text(md + f"\n![净值与回撤]({png_path.name})\n")
    plt.rcParams["font.sans-serif"] = ["PingFang SC", "Heiti SC", "Arial Unicode MS"]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    ax1.plot(nav.index, nav.values)
    ax1.set_title("今天的持仓比例放回历史（澳元，每日再平衡）")
    dd = drawdown(nav)
    ax2.fill_between(dd.index, dd.values, 0, color="tab:red", alpha=0.4)
    ax2.axhline(-0.20, color="black", ls="--", lw=1, label="-20% 上限")
    ax2.legend(loc="lower left")
    ax2.set_title("回撤")
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
    print(f"已生成：{md_path}  {png_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
