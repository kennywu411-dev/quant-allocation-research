import pandas as pd

from quant.research.p5 import render


def _orders():
    return pd.DataFrame([{"symbol": "AAPL", "side": "卖", "shares": 7, "price": 100.0, "value": 700.0, "cost": 1.0},
                         {"symbol": "CASH", "side": "剩余", "shares": 0, "price": 1.0, "value": 10.0, "cost": 0.0}])


def test_render_sections():
    rules = pd.DataFrame({"p_breach20": [0.3, 0.05], "p_breach15": [0.6, 0.6], "median_cagr": [0.06, 0.055],
                          "p5_cagr": [0.0, 0.01], "median_mdd": [-0.18, -0.16], "p5_mdd": [-0.3, -0.2],
                          "mean_switches": [0.0, 1.5], "p_trigger": [0.0, 0.6]}, index=["无规则", "清零-回升"])
    tax = pd.DataFrame([{"symbol": "AAPL", "shares": 7, "price": 100.0, "cost_basis": "待补", "gain": "待补",
                         "held_days": "待补", "discount_eligible": "待补"}])
    ctx = {"as_of": pd.Timestamp("2026-10-31").date(), "w_us": 0.5,
           "accounts": {"美股账户": {"base": {"SPY": 0.6}, "sig_date": pd.Timestamp("2026-10-30"), "target": {"SPY": 0.6},
                                     "ccy": "USD", "nav": 20000.0,
                                     "price_date": pd.Timestamp("2026-10-20"), "stale": True}},
           "perf": {"is": 0.06, "oos": 0.058, "full": 0.059, "mdd": -0.142, "window": "2007-06-01 至 2026-10-30",
                    "periods": {"2008 金融危机": 0.075}},
           "rules": rules, "pick": "清零-回升", "hist": {"无规则": (0, -0.142), "清零-回升": (0, -0.142)},
           "boot": {"n_paths": 2000, "length": 2520, "mean_block": 63, "seed": 20261031},
           "orders": {"美股账户": _orders()}, "hist_mdd": {"core": -0.119, "def": -0.162}, "tranches": {"美股账户": [_orders()] * 3}, "tax": tax}
    md = render(ctx)
    for h in ["目标配置", "风控规则", "过渡方案", "税务", "每月操作", "声明", "清零-回升", "待补", "20261031",
              "仅供参考", "价格日期 2026-10-20", "可能过期", "份额", "-16.2%"]:
        assert h in md, h
    ctx["pick"] = "无规则"
    ops = render(ctx).split("## 每月操作")[1].split("##")[0]
    assert "执行风控规则" not in ops and "复盘" in ops


def test_defensive_moves_equity_to_safe_only():
    from quant.research.p5 import defensive_weights
    a = {"eq": ["510300", "510880"], "safe": "511010"}
    base = {"510300": 0.15, "510880": 0.15, "511010": 0.35, "518880": 0.35}
    d = defensive_weights(base, a)
    assert d["510300"] == 0 and d["510880"] == 0
    assert abs(d["511010"] - 0.65) < 1e-12 and d["518880"] == 0.35


def test_user_decision_replaces_question():
    rules = pd.DataFrame({"p_breach20": [0.0215, 0.016], "p_breach15": [0.15, 0.15], "median_cagr": [0.0572, 0.0572],
                          "p5_cagr": [0.02, 0.02], "median_mdd": [-0.11, -0.11], "p5_mdd": [-0.18, -0.18],
                          "mean_switches": [0.0, 0.3], "p_trigger": [0.0, 0.15]}, index=["无规则", "减半-回升"])
    from quant.research import p5
    md = p5.render_rules(rules, "无规则", decision=p5.DECISION)
    assert "需要你决定" not in md
    assert "你的决定（2026-10-31）" in md and "只提醒不交易" in md
    md2 = p5.render_rules(rules, "无规则", decision=None)
    assert "需要你决定" in md2
