import pandas as pd

from quant.research.aggr_report import render


def _orders():
    return pd.DataFrame([{"symbol": "AAPL", "side": "卖", "shares": 7, "price": 100.0, "value": 700.0, "cost": 1.0},
                         {"symbol": "QQQ", "side": "买", "shares": 20, "price": 600.0, "value": 12000.0, "cost": 1.0},
                         {"symbol": "CASH", "side": "剩余", "shares": 0, "price": 1.0, "value": 10.0, "cost": 0.0}])


def _ctx(mdd=-0.295):
    perf = {"is": 0.093, "oos": 0.161, "full": 0.116, "mdd": mdd, "periods": {"2008 金融危机": -0.25},
            "window": "2007-06-01 至 2026-09-30", "years": {2008: -0.2, 2022: -0.15}}
    cur = {"is": 0.06, "oos": 0.058, "full": 0.059, "mdd": -0.142, "periods": {"2008 金融危机": -0.05}, "years": {2008: -0.03}}
    return {"as_of": "2026-11-04", "pick": ("美股账户｜QQQ｜股90%｜static", "P3｜A股账户｜股10%｜债金2比1｜sma10_bond"),
            "w_us": 0.53, "perf": perf, "current": cur,
            "boot": {"p_cap": 0.21, "p_deep": 0.05, "median_cagr": 0.10, "p5_cagr": 0.01, "median_mdd": -0.24,
                     "n_paths": 2000, "length": 2520, "mean_block": 63, "seed": 20261031},
            "accounts": {"美股账户": {"target": {"QQQ": 0.9, "IEF": 0.025, "TLT": 0.025, "GLD": 0.05},
                                      "sig_date": pd.Timestamp("2026-10-30"), "ccy": "USD", "orders": _orders(),
                                      "price_date": pd.Timestamp("2026-11-03")}},
            "lev": {"crash_1987": -0.348, "te": {"SSO": 0.0014}, "best_lev": "QLD｜股100%｜static", "best_lev_mdd": -0.845},
            "mom": {"bias": 0.08, "real_cagr": 0.22, "french_cagr": 0.14}, "n_ok": 270, "expanded": True}


def test_render_sections():
    md = render(_ctx())
    for h in ["与现行方案对比", "自助法", "杠杆", "幸存者偏差", "调到目标", "需要你决定", "声明", "几乎贴线", "候选扩充"]:
        assert h in md, h
    table = md.split("调到目标")[1]
    assert "MOMBIG" not in table


def test_no_tight_warning_with_margin():
    assert "几乎贴线" not in render(_ctx(mdd=-0.25))


def test_w_us_sensitivity_and_cn_note():
    ctx = _ctx()
    ctx["sens"] = {0.50: (0.112, -0.285), 0.55: (0.118, -0.302), 0.60: (0.123, -0.318)}
    md = render(ctx)
    assert "美股占比敏感性" in md and "55%" in md
    assert "A股的激进候选都没有用上" in md


def test_cap_and_leverage_pick():
    ctx = _ctx(mdd=-0.49)
    ctx.update(mdd=-0.50, pick=("美股账户｜QLD｜股80%｜static", "A股账户｜512100｜股80%｜sma10_bond"),
               sens={0.55: (0.18, -0.47), 0.60: (0.19, -0.51)}, close_calls="**选中和第二名只差 0.0 个百分点**")
    ctx["lev"]["dot_com"] = (-0.83, -0.97)
    md = render(ctx)
    assert "跌破 -30%" not in md and "满足 -30%" not in md and "≥ -30%" not in md
    for h in ["合并回撤 ≥ -50%", "跌破 -50%", "跌破 -60%", "杠杆的风险", "-97.0%", "只差 0.0", "满足 -50%"]:
        assert h in md, h
    assert "A股的激进候选都没有用上" not in md


def test_us_value_override_table():
    ctx = _ctx()
    o = pd.DataFrame([{"symbol": "QLD", "weight": 0.8, "shares": 150, "price": 120.0, "value": 18000.0},
                      {"symbol": "CASH", "weight": 0.0, "shares": 0, "price": 1.0, "value": 50.0}])
    ctx["accounts"]["美股账户"].update(orders=o, value_override=10000.0)
    md = render(ctx)
    assert "10,000" in md and "| QLD | 80.0% | 150 |" in md
