import numpy as np
import pandas as pd

from quant.factors import calc, evaluate as ev

ME = pd.date_range("2020-01-31", periods=14, freq="ME")


def test_dividend_ttm_window_and_status():
    div = pd.DataFrame({"ex_date": pd.to_datetime(["2020-06-15", "2021-06-15", "2021-08-01"]),
                        "cash_per10": [3.0, 5.0, 2.0], "status": ["实施", "实施", "预案"]})
    s = calc.dividend_ttm(div, pd.DatetimeIndex(["2021-05-31", "2021-06-30", "2021-08-31"]))
    assert s.tolist() == [0.3, 0.5, 0.5]  # 12 个月窗口；每 10 股折成每股；预案不计


def test_momentum_skips_last_month_and_reversal():
    close = pd.DataFrame({"A": np.arange(1, 15, dtype=float)}, index=ME)
    p = {"close": close, "pe": close * 0 + 10, "pb": close * 0 + 2, "div_ttm": close * 0, "raw_close": close,
         "vol252": close * 0 + 0.02, "turn20": close * 0 + 1.5}
    f = calc.factor_values(p)
    t = ME[12]
    assert f["MOM12_1"].loc[t, "A"] == close.loc[ME[11], "A"] / close.loc[ME[0], "A"] - 1
    assert f["REV1"].loc[t, "A"] == -(close.loc[t, "A"] / close.loc[ME[11], "A"] - 1)
    assert f["EP"].loc[t, "A"] == 0.1 and f["LOWVOL"].loc[t, "A"] == -0.02 and f["LOWTURN"].loc[t, "A"] == -1.5


def test_bp_drops_negative_book():
    pb = pd.DataFrame({"A": [2.0], "B": [-1.0]}, index=ME[:1])
    z = pb * 0
    f = calc.factor_values({"close": z + 1, "pe": z + 1, "pb": pb, "div_ttm": z, "raw_close": z + 1, "vol252": z, "turn20": z})
    assert f["BP"].loc[ME[0], "A"] == 0.5 and np.isnan(f["BP"].loc[ME[0], "B"])


def test_universe_requires_member_trading_not_st():
    idx = ME[:1]
    member = pd.DataFrame({"A": [True], "B": [True], "C": [True], "D": [False]}, index=idx)
    last = pd.Timestamp("2020-01-23")
    p = {"last_date": pd.DataFrame({"A": [last], "B": [pd.Timestamp("2020-01-20")], "C": [last], "D": [last]}, index=idx),
         "status": pd.DataFrame({"A": [1.0], "B": [1.0], "C": [1.0], "D": [1.0]}, index=idx),
         "isST": pd.DataFrame({"A": [0.0], "B": [0.0], "C": [1.0], "D": [0.0]}, index=idx)}
    u = calc.universe(member, p, pd.Series([last], index=idx))
    assert u.loc[ME[0]].tolist() == [True, False, False, False]  # B 月末停牌、C 是 ST、D 不是成分


def test_members_panel_by_month():
    m = pd.DataFrame({"month_end": ["2020-01-31", "2020-02-28"], "update_date": ["2020-01-20", "2020-02-24"],
                      "code": ["sh.600000", "sz.000001"]})
    p = calc.members_panel(m, ME[:2], ["sh.600000", "sz.000001"])
    assert p.values.tolist() == [[True, False], [False, True]]


def test_preprocess_zscore_and_winsor():
    x = pd.Series(list(range(100)) + [10_000], dtype=float)
    z = ev.preprocess(x)
    assert abs(z.mean()) < 1e-12 and abs(z.std() - 1) < 1e-12
    assert z[100] == z.max() and z.max() < 2  # 极端值被缩尾


def _toy(n=60, months=4, sign=1.0):
    idx = ME[:months]
    cols = [f"S{i}" for i in range(n)]
    f = pd.DataFrame(np.tile(np.arange(n, dtype=float), (months, 1)), index=idx, columns=cols)
    fwd = f * 0.001 * sign
    mask = pd.DataFrame(True, index=idx, columns=cols)
    return f, fwd, mask


def test_rank_ic_perfect_and_negative():
    f, fwd, mask = _toy()
    assert np.allclose(ev.ic_series(f, fwd, mask), 1.0)
    f, fwd, mask = _toy(sign=-1)
    assert np.allclose(ev.ic_series(f, fwd, mask), -1.0)


def test_ic_summary_and_verdict():
    ic = pd.Series([0.05, 0.03, 0.04, 0.06] * 6)
    s = ev.ic_summary(ic)
    assert abs(s["t"] - s["mean"] / s["std"] * np.sqrt(24)) < 1e-12 and s["win"] == 1.0
    assert ev.verdict({"t": 3.5, "mean": 0.03}, {"mean": 0.01}) == "显著"
    assert ev.verdict({"t": 3.5, "mean": 0.03}, {"mean": -0.01}) == "不显著"
    assert ev.verdict({"t": 2.4, "mean": 0.03}, {"mean": 0.01}) == "弱"
    assert ev.verdict({"t": -2.4, "mean": -0.03}, {"mean": -0.01}) == "方向相反"


def test_groups_order_and_long_short():
    f, fwd, mask = _toy()
    grp = ev.groups(f, mask, fwd)
    gr = ev.group_returns(grp, fwd)
    assert list(gr.columns) == [1, 2, 3, 4, 5]
    assert (gr.diff(axis=1).iloc[:, 1:] > 0).all().all()  # 组号越高收益越高
    assert gr.index[0] == ME[1]  # 收益记在持有月
    ls = ev.long_short(gr, grp)
    assert ls.top_turn.iloc[0] == 1.0 and ls.top_turn.iloc[1] == 0.0  # 首月建仓，之后持仓不变
    assert ls.ls_net.iloc[1] == ls.ls.iloc[1]  # 没有换手就没有成本


def test_turnover_partial():
    grp = {ME[0]: {1: ["A", "B", "C", "D"]}, ME[1]: {1: ["A", "B", "E", "F"]}}
    assert ev.turnover(grp, 1).tolist() == [1.0, 0.5]


def test_cost_rate_stamp_cut():
    assert abs(ev.cost_rate(pd.Timestamp("2023-01-31")) - 0.0035) < 1e-12
    assert abs(ev.cost_rate(pd.Timestamp("2023-09-30")) - 0.003) < 1e-12


def test_current_path_code_and_asof_valuation():
    from quant.factors import data_current as dc
    assert dc.to_code("600000", "上海证券交易所") == "sh.600000" and dc.to_code("000001", "深圳证券交易所") == "sz.000001"
    px = pd.DataFrame({"date": ["2020-01-02", "2020-01-20", "2020-02-05"], "close": [10, 11, 12],
                       "amount": [1, 1, 1], "turnover": [0.005, 0.006, 0.007]})
    pe = pd.DataFrame({"date": ["2019-12-25", "2020-01-16"], "value": [8.0, -4.0]})
    pb = pd.DataFrame({"date": ["2020-01-03"], "value": [1.2]})
    d = dc.build_daily(px, pe, pb, "sh.600000")
    assert d.peTTM.tolist() == [8.0, -4.0, -4.0]  # 只用当天及以前的估值点
    assert np.isnan(d.pbMRQ[0]) and d.pbMRQ[1] == 1.2
    assert np.allclose(d.turn, [0.5, 0.6, 0.7])  # 新浪是小数，换成百分比
    assert (d.tradestatus == 1).all() and list(d.columns[:5]) == ["date", "code", "close", "amount", "turn"]


def test_analyze_and_render_end_to_end():
    from quant.factors import run
    idx = pd.date_range("2018-01-31", periods=36, freq="ME")
    rng = np.random.default_rng(0)
    cols = [f"S{i}" for i in range(60)]
    f = pd.DataFrame(rng.normal(size=(36, 60)), index=idx, columns=cols)
    fwd = f * 0.01 + rng.normal(scale=0.002, size=(36, 60))  # 因子与下月收益强正相关
    fwd.iloc[-1] = np.nan
    univ = pd.DataFrame(True, index=idx, columns=cols)
    r = run.analyze(f, fwd, univ)
    s = r["summary"]
    assert s["rank_ic"] > 0.8 and s["verdict"] == "显著" and s["n_months"] == 35
    assert s["q5"] > s["q1"] and s["ls_gross"] > s["ls_net"]  # 有换手就有成本
    res = {k: r for k in calc.FACTORS}
    S = {k: s for k in calc.FACTORS}
    meta = {"date": "2026-11-10", "source": "current", "label": "测试", "n_codes": 60, "run_id": "x",
            "sources": {"daily": "合成"}, "conclusion": run.conclusion(S, "current"), "download": "m"}
    md = run.render(res, meta, "x.png")
    assert "幸存者偏差" in md and md.count("| **显著** |") == len(calc.FACTORS)


def test_universe_excludes_recent_ipo():
    idx = ME[:1]
    last = pd.Timestamp("2020-01-23")
    member = pd.DataFrame({"A": [True], "B": [True]}, index=idx)
    p = {"last_date": pd.DataFrame({"A": [last], "B": [last]}, index=idx),
         "status": pd.DataFrame({"A": [1.0], "B": [1.0]}, index=idx),
         "isST": pd.DataFrame({"A": [0.0], "B": [0.0]}, index=idx),
         "age": pd.DataFrame({"A": [252.0], "B": [251.0]}, index=idx)}
    assert calc.universe(member, p, pd.Series([last], index=idx)).loc[ME[0]].tolist() == [True, False]


def test_stock_monthly_age_counts_traded_days():
    d = pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=30), "close": 1.0, "turn": 1.0, "isST": 0.0,
                      "peTTM": 1.0, "pbMRQ": 1.0, "tradestatus": [1.0] * 25 + [0.0] * 5})
    m = calc.stock_monthly(d)
    assert m.age.iloc[0] == 23 and m.age.iloc[-1] == 25  # 1 月 23 个交易日；停牌日不计
