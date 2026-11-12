"""因子库框架：注册表、体检报告，以及用新框架复现第一轮、第二轮已记录数字的回归测试。"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant.alpha import spec
from quant.factors import evaluate as fev


def synth(n_months=30, n_codes=200, seed=0):
    """合成数据：GOOD 因子与下月收益正相关，SIZE 与收益无关。"""
    rng = np.random.default_rng(seed)
    rb = pd.date_range("2018-01-31", periods=n_months, freq="ME")
    codes = [f"sz.{k:06d}" for k in range(n_codes)]
    df = lambda a: pd.DataFrame(a, index=rb, columns=codes)
    good = df(rng.normal(size=(n_months, n_codes)))
    size = df(rng.normal(size=(n_months, n_codes)))
    fwd = good * 0.02 + df(rng.normal(scale=0.01, size=(n_months, n_codes)))
    fwd.iloc[-1] = np.nan
    yes, no = df(True), df(False)
    return {"rb": rb, "f": {"GOOD": good, "SIZE": size}, "fwd": fwd, "univ": yes, "up": no, "dn": no, "tradable": yes,
            "mcap": np.exp(-size)}


def test_register_makes_factor_computable_by_name():
    from quant.alpha import registry as R
    reg = {}

    @R.register("TOY", "玩具因子 = 收盘价", registry=reg)
    def toy(ctx):
        return ctx.w["close"].reindex(ctx.rb)

    rb = pd.DatetimeIndex(["2024-01-26"])
    w = {"close": pd.DataFrame({"A": [3.0]}, index=rb)}
    out = R.compute(["TOY"], R.Ctx(w, rb), registry=reg)
    assert out["TOY"].loc[rb[0], "A"] == 3.0 and reg["TOY"].desc == "玩具因子 = 收盘价"


def test_register_rejects_duplicate_name():
    from quant.alpha import registry as R
    reg = {}
    R.register("X", "一", registry=reg)(lambda ctx: None)
    with pytest.raises(ValueError):
        R.register("X", "二", registry=reg)(lambda ctx: None)


def test_library_registers_exactly_the_preregistered_weekly_factors():
    from quant.alpha import library  # noqa: F401  导入即登记
    from quant.alpha import registry as R
    assert set(R.REGISTRY) == set(spec.W_FACTORS)
    assert all(R.REGISTRY[k].desc == v for k, v in spec.W_FACTORS.items())


def test_checkup_refuses_factor_without_preregistration():
    from quant.alpha import checkup as C
    b = synth()
    with pytest.raises(PermissionError):
        C.checkup("GOOD", b)  # GOOD 不在 spec 的登记名单里：先登记再看结果


def test_checkup_reports_ic_groups_turnover_longonly_and_size_neutral():
    from quant.alpha import checkup as C
    r = C.checkup("GOOD", synth(), allow_unregistered=True)
    assert r["ic"]["rank_ic"] > 0.5 and r["ic"]["t"] > 3
    g = r["groups"]["ann"]
    assert len(g) == 5 and all(g[i] < g[i + 1] for i in range(4))  # 五分组单调
    assert 0 < r["cost"]["top_turn"] <= 1 and r["cost"]["cost_drag_ann"] > 0
    assert r["long_only"]["ex_ann"] > 0 and "ex_t" in r["long_only"]
    assert r["size_neutral"]["rank_ic"] > 0.5 and r["size_neutral"]["long_only"]["ex_ann"] > 0
    assert r["industry_neutral"] == "未做：没有行业分类数据"


def test_checkup_size_neutral_not_applicable_to_size_itself():
    from quant.alpha import checkup as C
    r = C.checkup("SIZE", synth())
    assert r["size_neutral"] == "不适用：因子本身就是市值"


def test_checkup_markdown_has_all_sections():
    from quant.alpha import checkup as C
    md = C.render(C.checkup("GOOD", synth(), allow_unregistered=True))
    for h in ("RankIC", "五分组", "换手与成本", "纯多头", "市值中性", "行业中性"):
        assert h in md
    assert "不是投资建议" in md


# ───────── 回归：新框架必须复现已记录的数字（需要本机周线缓存）─────────
CACHE = Path("data/cache/alpha/weekly")
need_cache = pytest.mark.skipif(not (CACHE / "meta.json").exists() or not Path("research/alpha_results.json").exists(),
                                reason="没有周线缓存或第一轮结果文件")


@pytest.fixture(scope="module")
def real():
    from quant.alpha.weekly import build
    return build()


@need_cache
def test_regression_round1_single_factors_and_linear_composites(real):
    from quant.alpha import checkup as C
    rec = json.loads(Path("research/alpha_results.json").read_text())["factors"]
    for name in [*spec.W_FACTORS, "等权合成", "IC加权合成"]:
        r = C.checkup(name, real)
        for k in ("rank_ic", "t", "oos_rank_ic", "ex_ann", "oos_ex_ann", "top_turn", "passed"):
            assert r["round1"][k] == pytest.approx(rec[name][k], rel=1e-9, abs=1e-12), (name, k)


@need_cache
def test_regression_round2_portfolios(real):
    from quant.alpha import checkup as C
    rec = json.loads(Path("research/alpha_round2.json").read_text())["trials"]
    got = {"等权合成+缓冲带": C.checkup("等权合成", real)["buffered"],
           "慢因子合成+缓冲带": C.checkup("慢因子合成", real)["buffered"],
           "慢因子合成": C.checkup("慢因子合成", real)["long_only"],
           "等权合成（市值中性）": C.checkup("等权合成", real)["size_neutral"]["long_only"],
           "IVOL（市值中性）": C.checkup("IVOL", real)["size_neutral"]["long_only"]}
    for name, s in got.items():
        for k in ("ex_ann", "ex_t", "oos_ex_ann", "top_turn", "n_hold"):
            assert s[k] == pytest.approx(rec[name][k], rel=1e-9, abs=1e-12), (name, k)


# ───────── 勘误（2026-11-12）：持有月份标签重复导致丢月、最后一期没有下期收益却记了 0 ─────────
def _one_stock_world(rb):
    codes = [f"sz.{k:06d}" for k in range(120)]
    df = lambda v: pd.DataFrame(v, index=rb, columns=codes)
    return codes, df


def test_simulate_keeps_every_period_when_rebalance_falls_on_calendar_month_end():
    from quant.alpha import evaluate as E
    rb = pd.DatetimeIndex(["2026-06-26", "2026-07-31", "2026-08-28", "2026-09-25"])  # 07-31 既是周五也是自然月末
    codes, df = _one_stock_world(rb)
    fwd = df(0.0)
    fwd.loc["2026-07-31"] = 0.10
    fwd.loc["2026-08-28"] = 0.20
    fwd.loc["2026-09-25"] = np.nan
    sim = E.simulate({t: set(codes) for t in rb}, fwd, df(False), df(False), df(True))
    assert len(sim) == 3 and sim.index.is_unique  # 三个走完的持有期一个不少；最后一期没有下期收益，不出数
    assert sim.gross.tolist() == pytest.approx([0.0, 0.10, 0.20])
    assert list(sim.index) == list(pd.to_datetime(["2026-07-31", "2026-08-31", "2026-09-30"]))  # 标签 = 持有月份的月末


def test_group_returns_and_turnover_labels_are_unique():
    rb = pd.DatetimeIndex(["2026-06-26", "2026-07-31", "2026-08-28"])
    codes, df = _one_stock_world(rb)
    f = pd.DataFrame(np.tile(np.arange(120.0), (3, 1)), index=rb, columns=codes)
    grp = fev.groups(f, df(True), df(0.01))
    assert len(fev.group_returns(grp, df(0.01))) == 3 and fev.turnover(grp, 5).index.is_unique


def test_summarize_and_round2_evaluate_count_all_periods():
    from quant.alpha import evaluate as E, round2
    b = synth(n_months=40)
    b["rb"] = pd.DatetimeIndex([d - pd.Timedelta(days=(d.weekday() - 4) % 7) for d in b["rb"]])  # 每月最后一个周五
    for k in ("fwd", "univ", "up", "dn", "tradable"):
        b[k].index = b["rb"]
    for k in b["f"]:
        b["f"][k].index = b["rb"]
    assert sum(t.is_month_end for t in b["rb"]) > 0  # 样本里确实有落在自然月末的调仓日
    args = (b["fwd"], b["univ"], b["up"], b["dn"], b["tradable"])
    assert len(E.summarize(b["f"]["GOOD"], *args)["excess"]) == 39
    assert round2.evaluate(round2.top_sets(b["f"]["GOOD"], b["univ"]), *args)["summary"]["n"] == 39
