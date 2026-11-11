import numpy as np
import pandas as pd

from quant.alpha import calc


def test_limit_pct_by_board_and_st():
    dates = pd.DatetimeIndex(["2020-08-21", "2020-08-24"])
    codes = pd.Index(["sh.600000", "sh.688001", "sz.300001", "sz.000001"])
    st = pd.DataFrame({"sz.000001": [1.0, 1.0]}, index=dates)
    lim = calc.limit_pct(codes, dates, st)
    assert np.allclose(lim.loc["2020-08-21"].to_numpy(), [0.10, 0.20, 0.10, 0.05])
    assert np.isclose(lim.loc["2020-08-24", "sz.300001"], 0.20)


def test_limit_flags_rounding():
    d = pd.DatetimeIndex(["2024-01-02"])
    p = {"preclose": pd.DataFrame({"A": [10.05], "B": [10.0]}, index=d),
         "close": pd.DataFrame({"A": [11.06], "B": [9.0]}, index=d),
         "tradestatus": pd.DataFrame({"A": [1.0], "B": [1.0]}, index=d)}
    lim = pd.DataFrame(0.10, index=d, columns=["A", "B"])
    up, dn = calc.limit_flags(p, lim)
    assert bool(up.loc[d[0], "A"]) and not bool(dn.loc[d[0], "A"])  # 10.05×1.1=11.055 → 11.06 涨停
    assert bool(dn.loc[d[0], "B"])


def test_forward_returns_and_delisting():
    days = pd.bdate_range("2024-01-01", "2024-03-29")
    ret = pd.DataFrame({"A": 0.0, "B": 0.0}, index=days)
    ret.loc["2024-02-01", "A"] = 0.10
    ret.loc["2024-02-15":, "B"] = np.nan  # B 2 月中退市
    ret.loc["2024-02-05", "B"] = -0.5
    me = calc.month_end_dates(days)
    fwd = calc.forward_returns(ret, me)
    assert abs(fwd.loc[me[0], "A"] - 0.10) < 1e-12 and abs(fwd.loc[me[0], "B"] + 0.5) < 1e-12
    assert fwd.loc[me[1], "B"] == 0.0 and pd.isna(fwd.loc[me[2], "A"])


def test_momentum_skips_current_month():
    days = pd.bdate_range("2023-01-02", "2024-02-29")
    ret = pd.DataFrame({"A": 0.0}, index=days)
    for m, r in [("2023-02", 0.2), ("2024-01", 0.5), ("2024-02", 0.9)]:
        ret.loc[ret.index.to_period("M") == m, "A"] = 0
        ret.loc[ret.index[ret.index.to_period("M") == m][0], "A"] = r
    me = calc.month_end_dates(days)
    p = {k: pd.DataFrame({"A": 1.0}, index=days) for k in ("peTTM", "pbMRQ", "turn", "tradestatus", "amount")}
    f = calc.factors(p, ret, pd.DataFrame({"A": 1e9}, index=days), me)
    t = me[-1]  # 2024-02：用 2023-03 至 2024-01，含 1 月的 +50%，不含 2 月和 2023-02
    assert abs(f["MOM12_1"].loc[t, "A"] - 0.5) < 1e-9
    assert abs(f["REV5"].loc[t, "A"]) < 1e-12 and f["SIZE"].loc[t, "A"] == -np.log(1e9)


def test_universe_filters_small_st_new_suspended():
    me = pd.DatetimeIndex(["2024-01-31"])
    days = pd.bdate_range("2022-01-03", "2024-01-31")
    codes = [f"sh.6000{k:02d}" for k in range(10)]
    full = lambda v: pd.DataFrame(v, index=days, columns=codes)
    p = {"close": full(1.0), "tradestatus": full(1.0), "volume": full(1.0), "isST": full(0.0)}
    p["isST"].loc[me[0], codes[9]] = 1.0
    p["tradestatus"].loc[me[0], codes[8]] = 0.0
    mcap = pd.DataFrame([np.arange(1, 11, dtype=float)] * len(days), index=days, columns=codes)
    basic = pd.DataFrame({"code": codes, "ipoDate": ["2010-01-01"] * 7 + ["2023-12-01"] + ["2010-01-01"] * 2})
    members = pd.DataFrame({"month_end": "2024-01-31", "code": codes})
    u = calc.universe(members, p, mcap, me, basic)
    # 先剔除 ST(9)、停牌(8)、上市不满一年(7)，剩 0–6 共 7 只，最小 30%（≤2.1 只）剔除 0、1
    assert u.loc[me[0]][u.loc[me[0]]].index.tolist() == codes[2:7]


def test_simulate_limit_up_blocks_buy_and_limit_down_blocks_sell():
    from quant.alpha.evaluate import simulate
    me = pd.DatetimeIndex(["2024-01-31", "2024-02-29", "2024-03-29"])
    cols = ["A", "B", "C"]
    fwd = pd.DataFrame([[0.10, 0.0, -0.10], [0.0, 0.05, -0.2], [0.0, 0.0, 0.0]], index=me, columns=cols)
    f = lambda v: pd.DataFrame(v, index=me, columns=cols)
    up = f([[False, True, False], [False, False, False], [False] * 3])
    dn = f([[False] * 3, [False, False, True], [False] * 3])
    tradable = f(True)
    target = {me[0]: {"A", "B", "C"}, me[1]: {"A", "B"}}
    r = simulate(target, fwd, up, dn, tradable)
    first = r.loc[pd.Timestamp("2024-02-29")]
    assert first.n == 2 and abs(first.gross - 0.0) < 1e-12  # B 涨停买不进：持有 A、C，(0.10 - 0.10) / 2
    second = r.loc[pd.Timestamp("2024-03-31")]
    assert second.n == 3  # C 跌停卖不出，B 补进来：A、B、C
    assert abs(second.turn - 1 / 3) < 1e-12 and second.net < second.gross


def test_ic_weighted_uses_only_past_ic():
    from quant.alpha.evaluate import ic_weighted
    idx = pd.date_range("2020-01-31", periods=14, freq="ME")
    z = {"F": pd.DataFrame(1.0, index=idx, columns=["A"]), "G": pd.DataFrame(-1.0, index=idx, columns=["A"])}
    ic = {"F": pd.Series(0.05, index=idx), "G": pd.Series(-0.05, index=idx)}
    ic["F"].iloc[12] = -9.0  # 第 13 个月的 IC 到第 14 个月才知道，不能影响第 13 个月的权重
    out = ic_weighted(z, ic, window=24)
    assert out.iloc[:12].isna().all().all()  # 不足 12 个月的历史 IC
    assert out.iloc[12, 0] == 1.0  # G 的历史 IC 为负 → 权重 0；只剩 F
    assert pd.isna(out.iloc[13, 0])  # 到第 14 个月 -9 才算进来：F 的均值变负，两个权重都为 0


def test_lgb_trains_only_on_realized_labels():
    from quant.alpha import evaluate as E
    from quant.alpha import spec
    idx = pd.date_range("2015-01-31", periods=40, freq="ME")
    rng = np.random.default_rng(0)
    cols = [f"S{k}" for k in range(300)]
    f = {k: pd.DataFrame(rng.normal(size=(40, 300)), index=idx, columns=cols) for k in spec.FACTORS}
    fwd = f["EP"] * 0.01  # 收益完全由 EP 决定
    univ = pd.DataFrame(True, index=idx, columns=cols)
    pred = E.lgb_composite(f, fwd, univ)
    first = pred.dropna(how="all").index[0]
    assert first == pd.Timestamp("2017-12-31")  # 2016-12 时只有 23 个月标签已实现（截到 2016-11），不够 24 个月
    c = pred.loc[first].corr(f["EP"].loc[first], method="spearman")
    assert c > 0.8


def test_weekly_alignment_and_rebalance_before_month_end():
    from quant.alpha.weekly import rebalance_dates, week_end
    d = pd.Series(pd.to_datetime(["2024-01-25", "2024-02-01", "2024-02-02"]))  # 周四（周五停牌）、周四、周五
    assert week_end(d).tolist() == [pd.Timestamp("2024-01-26"), pd.Timestamp("2024-02-02"), pd.Timestamp("2024-02-02")]
    weeks = pd.DatetimeIndex(pd.date_range("2024-01-05", "2024-03-29", freq="W-FRI"))
    rb = rebalance_dates(weeks)
    # 1 月 31 日是周三：1-26 那周之后的 2-02 周跨到 2 月，不能用；3-29 是周五，当周可用
    assert rb.tolist() == [pd.Timestamp("2024-01-26"), pd.Timestamp("2024-02-23"), pd.Timestamp("2024-03-29")]


def test_weekly_forward_and_momentum():
    from quant.alpha.weekly import factors, forward_returns
    wk = pd.date_range("2023-01-06", "2024-03-29", freq="W-FRI")
    ret = pd.DataFrame({"A": 0.0}, index=wk)
    ret.loc["2024-02-02", "A"] = 0.10
    w = {"ret": ret, "amount": pd.DataFrame({"A": 1e8}, index=wk), "turn": pd.DataFrame({"A": 1.0}, index=wk),
         "traded": pd.DataFrame({"A": True}, index=wk)}
    from quant.alpha.weekly import rebalance_dates
    rb = rebalance_dates(wk)
    fwd = forward_returns(w, rb)
    assert abs(fwd.loc[pd.Timestamp("2024-01-26"), "A"] - 0.10) < 1e-12  # 2-02 那周的收益算在 1 月调仓后的持有期
    f = factors(w, rb)
    assert abs(f["MOM12_1"].loc[pd.Timestamp("2024-03-29"), "A"] - 0.10) < 1e-12  # 2 月的 +10% 在 3 月调仓时算进动量
    assert f["MOM12_1"].loc[pd.Timestamp("2024-02-23"), "A"] == 0.0  # 2 月调仓时跳过当月
