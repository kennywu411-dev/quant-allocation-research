import pandas as pd

from quant.live.monthly import cash_first_orders, write_orders

ZERO = lambda s, side, v: 0.0  # noqa: E731
LOT = {"SPY": 1, "IEF": 1, "GLD": 1}


def _h(rows):
    return pd.DataFrame([{"account": "moomoo", "symbol": s, "shares": q} for s, q in rows])


def _side(o, s):
    r = o[o.symbol == s]
    return None if r.empty else (r.side.iloc[0], r.shares.iloc[0])


def test_cash_only_buys_underweight():
    o = cash_first_orders(_h([("SPY", 60), ("CASH", 4000)]), {"SPY": 100.0, "IEF": 100.0},
                          {"SPY": 0.6, "IEF": 0.4}, "moomoo", LOT, ZERO)
    assert _side(o, "SPY") is None
    assert _side(o, "IEF") == ("买", 40)
    assert o[o.symbol == "CASH"].value.iloc[0] >= 0


def test_sell_when_over_band():
    o = cash_first_orders(_h([("SPY", 80), ("IEF", 20)]), {"SPY": 100.0, "IEF": 100.0},
                          {"SPY": 0.6, "IEF": 0.4}, "moomoo", LOT, ZERO)
    assert _side(o, "SPY") == ("卖", 20)
    assert _side(o, "IEF") == ("买", 20)


def test_sell_when_target_zero():
    o = cash_first_orders(_h([("SPY", 60), ("GLD", 3)]), {"SPY": 100.0, "GLD": 100.0},
                          {"SPY": 1.0, "GLD": 0.0}, "moomoo", LOT, ZERO)
    assert _side(o, "GLD") == ("卖", 3)


def test_within_band_no_trade():
    o = cash_first_orders(_h([("SPY", 62), ("IEF", 38)]), {"SPY": 100.0, "IEF": 100.0},
                          {"SPY": 0.6, "IEF": 0.4}, "moomoo", LOT, ZERO)
    assert list(o.symbol) == ["CASH"]


def test_write_orders_idempotent(tmp_path):
    o = cash_first_orders(_h([("SPY", 60), ("CASH", 4000)]), {"SPY": 100.0, "IEF": 100.0},
                          {"SPY": 0.6, "IEF": 0.4}, "moomoo", LOT, ZERO)
    per = {"美股账户": {"orders": o, "ccy": "USD", "sig_date": pd.Timestamp("2026-10-30"),
                        "target": {"SPY": 0.6, "IEF": 0.4}, "price_date": pd.Timestamp("2026-10-30")}}
    write_orders("2026-11", per, tmp_path)
    write_orders("2026-11", per, tmp_path)
    files = sorted(p.name for p in (tmp_path / "2026-11").iterdir())
    assert "美股账户.csv" in files and "调仓单.md" in files and len(files) == 4  # 首版保留，重算版另存
    first = (tmp_path / "2026-11" / "调仓单.md").read_text()
    assert "生成于" in first and "声明" in first
    rerun = next(f for f in files if f.startswith("调仓单-重算"))
    assert "重算于" in (tmp_path / "2026-11" / rerun).read_text()
