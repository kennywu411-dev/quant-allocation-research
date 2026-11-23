"""第四轮（从信号到组合）：行业标签、中性化、风险模型不偷看未来、优化满足约束、容量与归因的算术。"""
import importlib.util

import numpy as np
import pandas as pd
import pytest

from quant.alpha import round4, spec

needs_cvxpy = pytest.mark.skipif(importlib.util.find_spec("cvxpy") is None, reason="没装 cvxpy")
N, T = 300, 40


@pytest.fixture(scope="module")
def panel():
    rng = np.random.default_rng(0)
    rb = pd.date_range("2015-01-31", periods=T, freq="ME")
    codes = pd.Index([f"sz.{i:06d}" for i in range(N)])
    lab = pd.Series(np.repeat(["C39", "C27", "J", "K", "I", "F"], N // 6), index=codes)
    univ = pd.DataFrame(True, index=rb, columns=codes)
    z = {k: pd.DataFrame(rng.normal(size=(T, N)), index=rb, columns=codes) for k in spec.R4_STYLES}
    true_f = pd.DataFrame(rng.normal(0, 0.02, (T, 5)), index=rb, columns=spec.R4_STYLES)
    ind_r = pd.DataFrame(rng.normal(0, 0.03, (T, 6)), index=rb, columns=["C39", "C27", "J", "K", "I", "F"])
    fwd = sum(z[k].mul(true_f[k], axis=0) for k in spec.R4_STYLES) + ind_r[lab.to_numpy()].to_numpy() \
        + pd.DataFrame(rng.normal(0, 0.05, (T, N)), index=rb, columns=codes)
    fwd.iloc[-1] = np.nan  # 最后一个调仓日没有下期收益
    return {"rb": rb, "codes": codes, "lab": lab, "univ": univ, "z": z, "fwd": fwd, "true_f": true_f, "rng": rng}


def test_industry_labels_rule(tmp_path):
    p = tmp_path / "ind.csv"
    pd.DataFrame({"code": ["a", "b", "c"], "industry": ["C39计算机", "J66货币金融服务", ""]}).to_csv(p, index=False)
    lab = round4.industry_labels(["a", "b", "c", "d"], p)
    assert list(lab) == ["C39", "J", "未知", "未知"]


def test_merge_small():
    lab = pd.Series(["x"] * 40 + ["y"] * 5)
    assert set(round4.merge_small(lab)) == {"x", "其他"}


def test_neutralize_removes_industry_and_size(panel):
    rng = np.random.default_rng(1)
    size = panel["z"]["SIZE"]
    bias = pd.Series(np.repeat([2.0, -1.0, 0.5, 0.0, 1.0, -2.0], N // 6), index=panel["codes"])
    f = pd.DataFrame(rng.normal(size=(T, N)), index=panel["rb"], columns=panel["codes"]) + bias + 0.8 * size
    out = round4.neutralize_ind_size(f, size, panel["univ"], panel["lab"])
    t = panel["rb"][3]
    assert out.loc[t].groupby(panel["lab"]).mean().abs().max() < 1e-9
    assert abs(out.loc[t].corr(size.loc[t])) < 1e-9


def test_factor_regression_recovers_planted_returns(panel):
    fr, res = round4.factor_regressions(panel["z"], panel["fwd"], panel["univ"], panel["lab"])
    assert len(fr) == T - 1  # 最后一期没有收益，不回归
    est = fr[[f"风格:{k}" for k in spec.R4_STYLES]].to_numpy()
    assert np.corrcoef(est.ravel(), panel["true_f"].iloc[:-1].to_numpy().ravel())[0, 1] > 0.9


def test_risk_uses_only_past_months(panel):
    fr, res = round4.factor_regressions(panel["z"], panel["fwd"], panel["univ"], panel["lab"])
    t = panel["rb"][30]
    cols = fr.columns
    a = round4.risk_at(t, cols, panel["codes"], fr, res)
    fr2, res2 = fr.copy(), res.copy()
    fr2.loc[fr2.index >= t] *= 50
    res2.loc[res2.index >= t] *= 50
    b = round4.risk_at(t, cols, panel["codes"], fr2, res2)
    assert np.allclose(a[0], b[0]) and np.allclose(a[1], b[1])
    assert round4.risk_at(panel["rb"][10], cols, panel["codes"], fr, res) is None  # 历史不足 24 个月


@needs_cvxpy
def test_optimizer_respects_constraints(panel):
    z, fwd, univ, lab = panel["z"], panel["fwd"], panel["univ"], panel["lab"]
    fr, res = round4.factor_regressions(z, fwd, univ, lab)
    sig = sum(z.values()) / len(z)
    no = pd.DataFrame(False, index=panel["rb"], columns=panel["codes"])
    up = no.copy()
    W, stat = round4.optimized_weights(sig, z, fwd, univ, up, no, ~no, lab, fr, res)
    ts = sorted(W)
    assert ts[0] == panel["rb"][spec.R4_COV_MIN] and stat["failed"] == 0
    for i, t in enumerate(ts[:6]):
        w = W[t].reindex(panel["codes"]).fillna(0.0)
        X = round4.exposures(t, z, univ, lab)
        act = w.to_numpy() - 1.0 / N
        assert abs(w.sum() - 1) < 1e-6 and w.min() >= 0 and w.max() <= spec.R4_W_MAX + 1e-4
        ind = [c for c in X.columns if c.startswith("行业:")]
        assert np.abs(X[ind].to_numpy().T @ act).max() <= spec.R4_IND_BAND + 1e-3
        assert abs(X["风格:SIZE"].to_numpy() @ act) <= spec.R4_SIZE_BAND + 1e-3
        F, D = round4.risk_at(t, X.columns, X.index, fr, res)
        te2 = act @ (X.to_numpy() @ F @ X.to_numpy().T) @ act + (D * act ** 2).sum()
        assert te2 * 12 <= spec.R4_TE ** 2 * 1.05
        if i:
            prev = W[ts[i - 1]].reindex(panel["codes"]).fillna(0.0)
            assert 0.5 * (w - prev).abs().sum() <= spec.R4_TURN + 1e-3
    # 信号高的股票权重更高
    t = ts[0]
    zt = sig.loc[t]
    assert W[t].reindex(panel["codes"]).fillna(0).corr(zt, method="spearman") > 0.3


@needs_cvxpy
def test_optimizer_limit_up_blocks_adding(panel):
    z, fwd, univ, lab = panel["z"], panel["fwd"], panel["univ"], panel["lab"]
    fr, res = round4.factor_regressions(z, fwd, univ, lab)
    sig = sum(z.values()) / len(z)
    no = pd.DataFrame(False, index=panel["rb"], columns=panel["codes"])
    t0 = panel["rb"][spec.R4_COV_MIN]
    best = sig.loc[t0].idxmax()
    up = no.copy()
    up.loc[t0, best] = True  # 第一期最想买的那只涨停
    W, _ = round4.optimized_weights(sig, z, fwd, univ, up, no, ~no, lab, fr, res)
    assert W[t0].get(best, 0.0) < 1e-6


def test_sets_weights_and_returns_match_simulate(panel):
    from quant.alpha import evaluate as E
    rb, codes, fwd, univ = panel["rb"], panel["codes"], panel["fwd"], panel["univ"]
    no = pd.DataFrame(False, index=rb, columns=codes)
    sig = sum(panel["z"].values())
    target = {t: s[1] for t, s in E.quantile_sets(sig, univ).items()}
    W = round4.sets_to_weights(target, no, no, ~no)
    R = round4.weight_returns(W, fwd, univ)
    sim = E.simulate(target, fwd, no, no, ~no)
    assert np.allclose(R.gross.astype(float).to_numpy(), sim.gross.to_numpy())
    assert np.allclose(R.turn.astype(float).to_numpy(), sim.turn.to_numpy())  # 等权、只数不变时两种换手口径一致


def test_impact_scales_with_sqrt_of_aum():
    t0, t1 = pd.Timestamp("2020-01-31"), pd.Timestamp("2020-02-29")
    W = {t0: pd.Series({"a": 0.5, "b": 0.5}), t1: pd.Series({"a": 0.5, "c": 0.5})}
    vol = pd.DataFrame(0.02, index=[t0, t1], columns=list("abc"))
    adv = pd.DataFrame(1e8, index=[t0, t1], columns=list("abc"))
    c1, c4 = round4.impact_costs(W, vol, adv, 1e8), round4.impact_costs(W, vol, adv, 4e8)
    # 第二期：卖 b 买 c，各 0.5；成交 5 千万 ÷ 日均 1 亿 = 0.5；冲击 = 0.02 × sqrt(0.5)，两笔各占净值 0.5
    assert c1.loc[t1, "impact"] == pytest.approx(2 * 0.5 * 0.02 * np.sqrt(0.5))
    assert c4.loc[t1, "impact"] == pytest.approx(2 * c1.loc[t1, "impact"])
    assert c1.loc[t1, "part_max"] == pytest.approx(0.5)


def test_capacity_zero_crossing_interpolates(monkeypatch):
    seq = iter([0.04, 0.02, -0.02, -0.05, -0.2])
    monkeypatch.setattr(round4.fev, "ann_return", lambda ex: next(seq))
    t0 = pd.Timestamp("2020-01-31")
    W = {t0: pd.Series({"a": 1.0})}
    R = pd.DataFrame({"t": [t0], "net": [0.01], "bench": [0.0], "gross": [0.01], "turn": [1.0]}, index=[t0])
    vol = pd.DataFrame(0.02, index=[t0], columns=["a"])
    adv = pd.DataFrame(1e8, index=[t0], columns=["a"])
    c = round4.capacity_table(W, R, vol, adv)
    assert c["zero_at"] == pytest.approx(1e8 + (5e8 - 1e8) * 0.02 / 0.04)


def test_attribution_parts_sum_to_active_return(panel):
    z, fwd, univ, lab = panel["z"], panel["fwd"], panel["univ"], panel["lab"]
    fr, _ = round4.factor_regressions(z, fwd, univ, lab)
    rng = np.random.default_rng(5)
    W = {t: pd.Series(rng.dirichlet(np.ones(N)), index=panel["codes"]) for t in panel["rb"][25:35]}
    a = round4.attribution(W, z, fwd, univ, lab, fr)["annual"]
    parts = a["行业"] + sum(a[k] for k in spec.R4_STYLES) + a["特质"]
    assert parts == pytest.approx(a["主动收益"], abs=1e-12)
