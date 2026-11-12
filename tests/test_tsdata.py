"""quant.tsdata 的离线单元测试：不联网，query 全部用假函数。"""
from datetime import date

import pandas as pd
import pytest

from quant.tsdata import download, store
from quant.tsdata.client import Client, NoPermission, RateLimiter

TODAY = date(2026, 11, 12)


def _client(query, **kw):
    return Client(query=query, sleep=lambda s: None, limiter=RateLimiter(1e9, sleep=lambda s: None), **kw)


def test_rate_limiter_spaces_calls_evenly():
    now, slept = [0.0], []

    def sleep(s):
        slept.append(s)
        now[0] += s

    rl = RateLimiter(120, clock=lambda: now[0], sleep=sleep)  # 每 0.5 秒一次
    for _ in range(4):
        rl.wait()
    assert slept == pytest.approx([0.5, 0.5, 0.5])


def test_fetch_pages_when_rows_hit_a_round_number():
    offsets = []

    def query(api, **p):
        offsets.append(p.get("offset", 0))
        n = {0: 1000, 1000: 1000, 2000: 37}[p.get("offset", 0)]
        return pd.DataFrame({"i": range(p.get("offset", 0), p.get("offset", 0) + n)})

    df = _client(query).fetch("daily", trade_date="20240102")
    assert offsets == [0, 1000, 2000]
    assert len(df) == 2037 and df.i.is_unique


def test_fetch_single_call_when_not_round_and_stops_if_offset_ignored():
    calls = []

    def query(api, **p):
        calls.append(p)
        return pd.DataFrame({"i": range(5574)})

    assert len(_client(query).fetch("daily", trade_date="20261111")) == 5574 and len(calls) == 1

    same = pd.DataFrame({"i": range(500)})
    assert len(_client(lambda api, **p: same.copy()).fetch("x")) == 500  # 接口忽略 offset 时不死循环、不重复


def test_fetch_pages_past_a_6400_cap_and_exhaustive_reads_until_empty():
    """实测 cashflow_vip 单次上限 6400（不是 500 的整数倍）：2023 年报第一页 6400 行，第二页 1851 行。"""
    def query(api, **p):
        off = p.get("offset", 0)
        return pd.DataFrame({"i": range(off, min(off + 6400, 8251))})

    assert len(_client(query).fetch("cashflow_vip", period="20231231")) == 8251

    offs = []

    def q2(api, **p):
        offs.append(p.get("offset", 0))
        off = p.get("offset", 0)
        return pd.DataFrame({"i": range(off, min(off + 77, 200))})  # 假想上限 77：只有 exhaustive 能取全

    assert len(_client(q2).fetch("x")) == 77
    offs.clear()
    assert len(_client(q2).fetch("x", exhaustive=True)) == 200 and offs == [0, 77, 154, 200]


def test_plan_force_refetches_cached(tmp_path):
    store.write("daily", "20240102", pd.DataFrame({"a": [1]}), tmp_path)
    assert download.plan(["daily"], ["20240102"], TODAY, 550, tmp_path)["daily"] == []
    assert len(download.plan(["daily"], ["20240102"], TODAY, 550, tmp_path, force=True)["daily"]) == 1


def test_retry_then_success_and_rate_error_sleeps_a_minute():
    slept, n = [], [0]

    def query(api, **p):
        n[0] += 1
        if n[0] == 1:
            raise Exception("抱歉，您每分钟最多访问该接口500次")
        if n[0] == 2:
            raise Exception("Connection reset")
        return pd.DataFrame({"a": [1]})

    c = Client(query=query, sleep=slept.append, limiter=RateLimiter(1e9, sleep=lambda s: None))
    assert len(c.fetch("daily")) == 1
    assert slept == [61, 6]


def test_permission_error_raises_no_permission_without_retry():
    n = [0]

    def query(api, **p):
        n[0] += 1
        raise Exception("抱歉，您没有接口访问权限，权限的具体详情访问：https://tushare.pro/document/1?doc_id=108")

    with pytest.raises(NoPermission):
        _client(query).fetch("stock_st", trade_date="20240102")
    assert n[0] == 1


def test_client_requires_token_env(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        Client()


def test_store_roundtrip_load_range_and_all_null_column(tmp_path):
    for d, v in (("20240102", 1.0), ("20240103", 2.0), ("20240104", 3.0)):
        store.write("daily", d, pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [d], "close": [v], "note": [None]}), tmp_path)
    store.write("daily", "20240105", pd.DataFrame(columns=["ts_code", "trade_date", "close", "note"]), tmp_path)
    assert store.keys("daily", tmp_path) == ["20240102", "20240103", "20240104", "20240105"]
    assert not list((tmp_path / "daily").glob("*.tmp"))
    df = store.load("daily", start="20240103", end="20240105", root=tmp_path)
    assert list(df.close) == [2.0, 3.0]
    assert store.load("income", root=tmp_path).empty


def test_periods_stop_at_last_quarter_end():
    ps = download.periods(2025, TODAY)
    assert ps == ["20250331", "20250630", "20250930", "20251231", "20260331", "20260630", "20260930"]


def test_plan_skips_cached_dates_and_refreshes_only_recent_stale_periods(tmp_path):
    empty = pd.DataFrame({"a": [1]})
    store.write("daily", "20240102", empty, tmp_path)
    old = store.write("income", "20100331_rt1", empty, tmp_path)
    recent = store.write("income", "20260930_rt1", empty, tmp_path)
    now = recent.stat().st_mtime
    jobs = download.plan(["daily", "income", "forecast"], ["20240102", "20240103"], TODAY, 550, tmp_path, now=now + 3600)
    assert jobs["daily"] == [("20240103", "daily", {"trade_date": "20240103"})]
    keys = [k for k, _, _ in jobs["income"]]
    assert "20100331_rt1" not in keys and "20260930_rt1" not in keys  # 刚写的近期分片不重拉
    assert "20100331_rt4" in keys and ("20260930_rt5", "income_vip", {"period": "20260930", "report_type": "5"}) in jobs["income"]
    assert jobs["forecast"][0] == ("20090331", "forecast_vip", {"period": "20090331"})
    later = download.plan(["income"], [], TODAY, 550, tmp_path, now=now + 30 * 3600)
    keys = [k for k, _, _ in later["income"]]
    assert "20260930_rt1" in keys and "20100331_rt1" not in keys  # 过了 20 小时：近期重拉，远期不动
    assert old.exists()


def test_run_jobs_resumable_empty_recent_not_cached_and_failures_reported(tmp_path):
    def query(api, **p):
        d = p["trade_date"]
        if d == "20240103":
            raise Exception("boom")
        if d == "20261112":
            return pd.DataFrame(columns=["ts_code", "trade_date"])
        return pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [d]})

    c = _client(query, retries=1)
    dates = ["20240102", "20240103", "20240104", "20261112"]
    jobs = download.plan(["daily"], dates, TODAY, 550, tmp_path)["daily"]
    r = download.run_jobs(c, "daily", jobs, 2, TODAY, tmp_path, log=lambda s: None)
    assert r["done"] == 2 and r["empty_skipped"] == ["20261112"]
    assert [f["key"] for f in r["failed"]] == ["20240103"]
    assert store.keys("daily", tmp_path) == ["20240102", "20240104"]
    again = download.plan(["daily"], dates, TODAY, 550, tmp_path)["daily"]
    assert [k for k, _, _ in again] == ["20240103", "20261112"]  # 续跑只剩失败的和没发布的


def test_run_jobs_skips_whole_dataset_without_permission(tmp_path):
    n = [0]

    def query(api, **p):
        n[0] += 1
        raise Exception("抱歉，您没有接口访问权限")

    jobs = [(d, "stock_st", {"trade_date": d}) for d in ("20240102", "20240103", "20240104")]
    r = download.run_jobs(_client(query), "stock_st", jobs, 2, TODAY, tmp_path, log=lambda s: None)
    assert r["no_permission"] and n[0] == 1 and store.keys("stock_st", tmp_path) == []
