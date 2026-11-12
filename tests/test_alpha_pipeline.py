"""月度流水线：调仓日判定、观察盘实际持仓与收益、数据源切换、监控告警、与回测的偏差。"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant.factors import evaluate as fev

FRI = lambda a, b: pd.date_range(a, b, freq="W-FRI")


def test_latest_complete_rebalance_waits_until_month_is_over():
    from quant.alpha import shadow as S
    assert S.latest_complete_rebalance(FRI("2026-09-04", "2026-11-13"), asof="2026-11-13") == pd.Timestamp("2026-10-30")
    assert S.latest_complete_rebalance(FRI("2026-09-04", "2026-11-20"), asof="2026-11-21") == pd.Timestamp("2026-10-30")
    assert S.latest_complete_rebalance(FRI("2026-09-04", "2026-11-27"), asof="2026-11-28") == pd.Timestamp("2026-11-27")


def test_latest_complete_rebalance_ignores_unfinished_week():
    from quant.alpha import shadow as S
    # 11-25（周三）拉数据，周线里已有一根对齐到 11-27 的半截周线：这一周还没走完，不能当调仓日
    assert S.latest_complete_rebalance(FRI("2026-09-04", "2026-11-27"), asof="2026-11-25") == pd.Timestamp("2026-10-30")


def test_actual_holdings_first_period_skips_limit_up():
    from quant.alpha import shadow as S
    held, turn = S.actual_holdings(set(), {"A", "B", "C"}, up={"C"}, dn=set(), untradable=set())
    assert held == {"A", "B"} and turn == 1.0


def test_actual_holdings_keeps_stuck_positions_and_counts_turnover():
    from quant.alpha import shadow as S
    held, turn = S.actual_holdings({"A", "B", "X", "Y"}, {"A", "B", "C", "D"}, up={"D"}, dn={"X"}, untradable=set())
    assert held == {"A", "B", "C", "X"}  # D 涨停买不进；X 跌停卖不出；Y 正常卖出
    assert turn == pytest.approx(1 / 4)


def _records():
    return [{"rebalance": "2026-10-30", "universe": ["A", "B"], "limit_up": [], "portfolios": {"P": ["A"]}},
            {"rebalance": "2026-11-27", "universe": ["A", "B"], "limit_up": [], "portfolios": {"P": ["B"]}}]


def _weekly_ret():
    wk = FRI("2026-10-30", "2026-11-27")
    ret = pd.DataFrame(0.0, index=wk, columns=["A", "B"])
    ret.loc["2026-10-30"] = [0.5, 0.5]  # 调仓周当周的收益不属于持有期
    ret.loc["2026-11-06", "A"] = 0.10
    ret.loc["2026-11-20", "B"] = -0.05
    return ret


def test_realized_returns_cover_only_the_holding_period_and_charge_cost():
    from quant.alpha import shadow as S
    df = S.realized(_records(), _weekly_ret())
    assert len(df) == 1  # 最后一期还没有终点，不出数字
    r = df.iloc[0]
    assert (r.start, r.end, r.portfolio, r.n) == ("2026-10-30", "2026-11-27", "P", 1)
    assert r.gross == pytest.approx(0.10) and r.bench == pytest.approx((0.10 - 0.05) / 2)
    assert r.net == pytest.approx(0.10 - 1.0 * fev.cost_rate(pd.Timestamp("2026-11-27")))
    assert r.excess == pytest.approx(r.net - r.bench)


def test_realized_returns_empty_with_single_record():
    from quant.alpha import shadow as S
    df = S.realized(_records()[:1], _weekly_ret())
    assert df.empty and list(df.columns) == S.RETURN_COLS


def test_realized_uses_recorded_held_when_present():
    from quant.alpha import shadow as S
    rec = _records()
    rec[0]["held"] = {"P": ["B"]}  # 记录里写明实际持仓时，以它为准
    assert S.realized(rec, _weekly_ret()).iloc[0].gross == pytest.approx(-0.05)


def test_update_data_cache_reports_freshness_and_other_sources_fail_loudly(tmp_path):
    from quant.alpha import pipeline as P
    pd.DataFrame({"date": pd.to_datetime(["2026-10-30", "2026-11-06"]), "close": [1.0, 1.0]}).to_parquet(tmp_path / "sh.600000.parquet")
    info = P.update_data("cache", cache=tmp_path)
    assert info["source"] == "cache" and info["last_week"] == "2026-11-06"
    for src in ("tushare", "baostock"):
        with pytest.raises(NotImplementedError):
            P.update_data(src, cache=tmp_path)
    with pytest.raises(ValueError):
        P.update_data("wind", cache=tmp_path)


def test_ic_alerts_flag_factors_whose_recent_ic_turned_negative():
    from quant.alpha import pipeline as P
    idx = pd.date_range("2022-01-31", periods=36, freq="ME")
    ok = pd.Series(0.05, index=idx)
    bad = pd.Series([0.05] * 24 + [-0.03] * 12, index=idx)
    a = P.ic_alerts({"OK": ok, "BAD": bad}, window=12)
    assert a["BAD"]["alert"] and not a["OK"]["alert"]
    assert a["BAD"]["recent"] == pytest.approx(-0.03) and a["BAD"]["full"] == pytest.approx((0.05 * 24 - 0.03 * 12) / 36)


def test_deviation_is_shadow_minus_backtest_per_period():
    from quant.alpha import pipeline as P
    real = pd.DataFrame([{"start": "2026-10-30", "end": "2026-11-27", "portfolio": "P", "gross": 0.03}])
    d = P.deviation(real, {"P": {"2026-10-30": 0.02}})
    assert d.iloc[0].backtest_gross == pytest.approx(0.02) and d.iloc[0]["diff"] == pytest.approx(0.01)


need_cache = pytest.mark.skipif(not Path("data/cache/alpha/weekly/meta.json").exists()
                                or not Path("live/alpha_shadow/2026-10-30.json").exists(), reason="没有周线缓存或观察盘首期记录")


@need_cache
def test_pipeline_end_to_end_reproduces_first_shadow_record(tmp_path):
    from quant.alpha import pipeline as P
    out = P.run(source="cache", asof="2026-11-12", shadow_dir=tmp_path / "shadow", report_dir=tmp_path, monitor_json=tmp_path / "m.json")
    old = json.loads(Path("live/alpha_shadow/2026-10-30.json").read_text())
    new = json.loads((tmp_path / "shadow" / "2026-10-30.json").read_text())
    assert out["rebalance"] == "2026-10-30" and out["recorded"] is True
    assert new["portfolios"] == old["portfolios"] and new["universe"] == old["universe"]
    assert set(new["held"]) == set(new["portfolios"])
    assert out["realized_periods"] == 0 and Path(out["report"]).exists()
    again = P.run(source="cache", asof="2026-11-12", shadow_dir=tmp_path / "shadow", report_dir=tmp_path, monitor_json=tmp_path / "m.json")
    assert again["recorded"] is False  # 已有记录不覆盖
    assert json.loads((tmp_path / "shadow" / "2026-10-30.json").read_text()) == new
