"""Tushare 日线 → 因子线周线缓存（与 baostock 周线同一格式），以及流水线的数据源切换。"""
import pandas as pd
import pytest


def test_code_mapping_matches_baostock_style():
    from quant.alpha import ts_weekly as T
    assert [T.code_of(c) for c in ("000001.SZ", "600000.SH", "430047.BJ")] == ["sz.000001", "sh.600000", "bj.430047"]


def _daily():
    rows = [("000001.SZ", "20261026", 10.0, 100.0, 1.0, 0.5), ("000001.SZ", "20261027", 11.0, 200.0, 10.0, 1.5),
            ("000001.SZ", "20261029", 9.9, 300.0, -10.0, 2.0),  # 周五 10-30 停牌：本周最后一个交易日是周四
            ("000001.SZ", "20261102", 10.0, 50.0, 1.0101, 0.25)]
    return pd.DataFrame(rows, columns=["ts_code", "trade_date", "close", "amount", "pct_chg", "turnover_rate"])


def test_to_weekly_aggregates_like_baostock_weekly_bars():
    from quant.alpha import ts_weekly as T
    w = T.to_weekly(_daily())
    assert list(w.columns) == ["date", "code", "close", "amount", "turn", "pctChg"] and len(w) == 2
    a = w.iloc[0]
    assert a.code == "sz.000001" and a.date == pd.Timestamp("2026-10-29")  # 日期 = 周内最后一个交易日
    assert a.close == 9.9 and a.amount == pytest.approx(600.0 * 1000)  # Tushare 成交额单位是千元 → 元
    assert a.turn == pytest.approx(4.0) and a.pctChg == pytest.approx((1.01 * 1.10 * 0.90 - 1) * 100)
    assert w.iloc[1].date == pd.Timestamp("2026-11-02")


def test_members_are_listed_and_not_delisted_at_month_end_and_skip_beijing():
    from quant.alpha import ts_weekly as T
    basic = pd.DataFrame({"ts_code": ["000001.SZ", "000002.SZ", "000003.SZ", "430047.BJ"],
                          "list_date": ["19910403", "20261015", "19910403", "20200101"],
                          "delist_date": [None, None, "20260915", None]})
    m = T.members(basic, pd.DatetimeIndex(["2026-09-30", "2026-10-30"]))
    got = {(str(r.month_end), r.code) for r in m.itertuples()}
    assert got == {("2026-09-30", "sz.000001"), ("2026-10-30", "sz.000001"), ("2026-10-30", "sz.000002")}


def _store(root):
    from quant.tsdata import store
    d = _daily()
    for day, g in d.groupby("trade_date"):
        store.write("daily", day, g[["ts_code", "trade_date", "close", "amount", "pct_chg"]], root)
        store.write("daily_basic", day, g[["ts_code", "trade_date", "turnover_rate"]], root)
    store.write("stock_basic", "all", pd.DataFrame({"ts_code": ["000001.SZ"], "list_date": ["19910403"], "delist_date": [None]}), root)


def test_convert_writes_weekly_files_members_and_basic(tmp_path):
    from quant.alpha import ts_weekly as T
    _store(tmp_path / "ts")
    info = T.convert(root=tmp_path / "ts", out=tmp_path / "alpha", start="20261001")
    w = pd.read_parquet(tmp_path / "alpha" / "weekly_ts" / "sz.000001.parquet")
    assert len(w) == 2 and info["files"] == 1 and info["last_day"] == "2026-11-02"
    mem = pd.read_csv(tmp_path / "alpha" / "all_members_ts.csv")
    assert set(mem.month_end) == {"2026-10-29", "2026-11-02"} and set(mem.code) == {"sz.000001"}  # 每月最后一个有行情的交易日
    assert pd.read_csv(tmp_path / "alpha" / "stock_basic_ts.csv").ipoDate.tolist() == ["1991-04-03"]


def test_pipeline_tushare_source_converts_from_local_tushare_cache(tmp_path):
    from quant.alpha import pipeline as P
    _store(tmp_path / "ts")
    info = P.update_data("tushare", ts_root=tmp_path / "ts", alpha_dir=tmp_path / "alpha")
    assert info["source"] == "tushare" and info["last_week"] == "2026-11-02" and info["files"] == 1
    paths = P.data_paths("tushare", alpha_dir=tmp_path / "alpha")
    assert paths["cache"] == tmp_path / "alpha" / "weekly_ts" and paths["members"].name == "all_members_ts.csv"
    assert P.data_paths("cache")["members"].name == "all_members.csv"


def test_coverage_counts_rows_dates_and_delisted_from_local_cache(tmp_path):
    from quant.alpha import ts_weekly as T
    from quant.tsdata import store
    root = tmp_path / "ts"
    _store(root)
    store.write("stock_basic", "all", pd.DataFrame({"ts_code": ["000001.SZ", "000002.SZ", "000003.SZ"], "list_date": ["19910403"] * 3,
                                                    "delist_date": [None, "20200101", "20120101"]}), root)
    store.write("daily", "20261103", pd.DataFrame({"ts_code": ["000002.SZ"], "trade_date": ["20261103"], "close": [1.0], "amount": [1.0], "pct_chg": [0.0]}), root)
    store.write("income", "20260930_rt1", pd.DataFrame({"ts_code": ["000001.SZ", "000002.SZ"], "ann_date": ["20261030", None], "f_ann_date": ["20261030", "20261031"]}), root)
    c = T.coverage(root)
    d = {x["name"]: x for x in c["datasets"]}
    assert d["daily"]["rows"] == 5 and d["daily"]["first"] == "20261026" and d["daily"]["last"] == "20261103" and d["daily"]["files"] == 5
    assert d["income"]["rows"] == 2 and d["income"]["first"] == "20260930" and "adj_factor" not in d  # 没有的数据集不列
    assert c["total_rows"] == sum(x["rows"] for x in c["datasets"]) == 5 + 4 + 2
    assert (c["stocks"], c["delisted"], c["daily_stocks"], c["delisted_with_daily"]) == (3, 2, 2, 1)
    assert c["statement_rows"] == 2 and c["ann_date_missing"] == 1 and c["f_ann_date_missing"] == 0
