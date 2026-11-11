import pandas as pd

from quant.llm_events import data


def test_tidy_dedup_and_id():
    raw = pd.DataFrame({"公告标题": [" A公司回购报告书 ", "A公司回购报告书", "A公司年报"],
                        "公告时间": ["2025-12-25 00:00:00", "2025-12-25 00:00:00", "2025-03-30 00:00:00"],
                        "公告链接": ["u1", "u1", "u2"]})
    d = data.tidy(raw, "sh.600000")
    assert len(d) == 2 and d.date.iloc[0] == pd.Timestamp("2025-03-30")
    assert d.id.iloc[1] == data.ann_id("A公司回购报告书", "u1") and len(d.id.iloc[0]) == 16


def test_mask_company_names():
    from quant.llm_events.label import mask
    assert mask("贵州茅台关于回购股份的公告", ["贵州茅台"]) == "本公司关于回购股份的公告"
    assert mask("北京市环球律师事务所关于贵州茅台酒股份有限公司控股股东增持之法律意见书", ["贵州茅台"]) == \
        "北京市环球律师事务所关于本公司控股股东增持之法律意见书"


def test_chunk_and_parse_roundtrip():
    from quant.llm_events.label import chunk_requests, parse_items
    df = pd.DataFrame({"id": [f"x{k}" for k in range(120)], "masked": ["本公司回购"] * 120})
    reqs = chunk_requests(df, "claude-haiku-5-5")
    assert [len(r["ids"]) for r in reqs] == [50, 50, 20]
    p = reqs[0]["params"]
    assert p["thinking"] == {"type": "disabled"} and p["output_config"]["effort"] == "low"
    assert "thinking" not in chunk_requests(df, "claude-haiku-4-5")[0]["params"]
    out = parse_items('{"items":[{"i":0,"type":"回购","direction":"利好","strength":2,"material":true},'
                      '{"i":99,"type":"其他","direction":"中性","strength":0,"material":false}]}', reqs[2]["ids"])
    assert out.id.tolist() == ["x100"] and out.direction.iloc[0] == "利好"  # 越界编号丢弃


def test_cost_batch_discount():
    from quant.llm_events.label import cost
    assert abs(cost("claude-haiku-5-5", 1_000_000, 1_000_000) - 0.30) < 1e-12
    assert abs(cost("claude-haiku-4-5", 1_000_000, 0, batch=False) - 1.0) < 1e-12


def test_dictionary_negative_wins_and_procedural():
    from quant.llm_events.dictionary import score
    assert score("本公司关于终止回购股份的公告")["direction"] == "利空"
    assert score("本公司关于控股股东增持股份的公告") == {"direction": "利好", "strength": 1, "material": True}
    assert score("关于本公司回购股份的法律意见书")["material"] is False
    assert score("本公司董事会决议公告")["direction"] == "中性"


def test_nw_t_matches_plain_t_without_lags():
    import numpy as np
    from quant.llm_events.study import nw_t
    x = pd.Series([0.01, 0.03, -0.01, 0.02, 0.00, 0.04])
    plain = x.mean() / (x.std(ddof=0) / np.sqrt(len(x)))
    assert abs(nw_t(x, 0) - plain) < 1e-12


def test_event_dates_next_trading_day():
    from quant.llm_events.study import event_dates
    cal = pd.DatetimeIndex(["2026-07-03", "2026-07-06", "2026-07-07"])
    t0 = event_dates(pd.Series(pd.to_datetime(["2026-07-04", "2026-07-06", "2026-07-08"])), cal)
    assert t0.iloc[0] == pd.Timestamp("2026-07-06") and t0.iloc[1] == pd.Timestamp("2026-07-06") and pd.isna(t0.iloc[2])


def test_calendar_series_excludes_t0_and_spread():
    from quant.llm_events.study import calendar_series, spread_stats
    days = pd.bdate_range("2026-07-01", periods=8)
    ar = pd.DataFrame({"A": [0.0, 0.05, 0.01, 0.01, 0.0, 0.0, 0.0, 0.0],
                       "B": [0.0, -0.05, -0.01, -0.01, 0.0, 0.0, 0.0, 0.0]}, index=days)
    ev = pd.DataFrame({"code": ["A", "B"], "t0": [days[1], days[1]], "group": ["利好", "利空"]})
    cs = calendar_series(ev, ar, k=2)
    assert list(cs.index) == [days[2], days[3]]  # 持有期第 1、2 天，不含 t0 当天的 ±5%
    s = spread_stats(cs, k=2)
    assert abs(s["car"] - 0.04) < 1e-12 and s["n_days"] == 2
    cs0 = calendar_series(ev, ar, k=2, include_t0=True)
    assert days[1] in cs0.index


def test_monthly_factor_rolls_last_day_to_next_month():
    from quant.llm_events.study import monthly_factor
    cal = pd.bdate_range("2026-07-01", "2026-08-31")
    e = pd.DataFrame({"code": ["A", "A", "A"], "material": [True, True, False],
                      "direction": ["利好", "利空", "利好"], "strength": [2, 1, 3],
                      "date": pd.to_datetime(["2026-07-10", "2026-07-31", "2026-07-15"])})
    f = monthly_factor(e, cal, pd.DatetimeIndex(["2026-07-31", "2026-08-31"]))
    assert f.loc["2026-07-31", "A"] == 2 and f.loc["2026-08-31", "A"] == -1  # 7-31 是最后交易日 → 算 8 月
