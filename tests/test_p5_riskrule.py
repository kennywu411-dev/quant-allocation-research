import numpy as np
import pandas as pd
import pytest

from quant.research.riskrule import RULES, Rule, block_bootstrap, overlay, pick_rule


def _r(vals):
    return pd.Series(vals, pd.bdate_range("2020-01-01", periods=len(vals)), dtype=float)


def test_rules_fixed():
    assert [r.name for r in RULES] == ["无规则", "减半-回升", "减半-3月", "清零-回升", "清零-3月"]


def test_overlay_none_equals_core():
    core = _r(np.random.default_rng(0).normal(0, 0.01, 300))
    nav, n = overlay(core, core * 0, Rule("无规则", 0.0, "dd"))
    assert nav.tolist() == pytest.approx((1 + core).cumprod().tolist())
    assert n == 0


def test_overlay_trigger_next_day():
    core = _r([-0.10, -0.10, 0.05, 0.05, 0.05])
    nav, n = overlay(core, core * 0, Rule("清零-回升", 1.0, "dd"))
    assert nav.iloc[1] == pytest.approx(0.81 * 0.998)  # 第 2 天收益仍按核心，收盘触发扣一次成本
    assert nav.iloc[2:].tolist() == pytest.approx([0.81 * 0.998] * 3)
    assert n == 1


def test_overlay_resume_uses_overlay_nav():
    core = _r([-0.10, -0.10] + [0.10] * 100)
    _, n_dd = overlay(core, core * 0, Rule("清零-回升", 1.0, "dd"))
    assert n_dd == 1  # 降仓后净值不动，回撤一直 -19%，不恢复
    nav, n_days = overlay(core, core * 0, Rule("清零-3月", 1.0, "days"))
    assert n_days == 2
    # 第 2 天触发，第 65 天（索引 64）收盘恢复并扣成本，第 66 天起按核心
    assert nav.iloc[64] == pytest.approx(0.81 * 0.998 * 0.998)
    assert nav.iloc[65] == pytest.approx(nav.iloc[64] * 1.10)


def test_overlay_half_cut():
    core = _r([-0.10, -0.10, 0.04])
    de = _r([0.0, 0.0, 0.02])
    nav, _ = overlay(core, de, Rule("减半-回升", 0.5, "dd"))
    assert nav.iloc[2] / nav.iloc[1] - 1 == pytest.approx(0.5 * 0.04 + 0.5 * 0.02)
    assert nav.iloc[1] == pytest.approx(0.81 * (1 - 0.002 * 0.5))


def test_bootstrap_pairs_and_shape():
    df = pd.DataFrame({"a": np.arange(100.0), "b": np.arange(1000.0, 1100.0)})
    x = block_bootstrap(df, 3, 50, 10, seed=1)
    assert x.shape == (3, 50, 2)
    assert np.all(x[:, :, 1] - x[:, :, 0] == 1000)
    assert np.array_equal(x, block_bootstrap(df, 3, 50, 10, seed=1))
    big = block_bootstrap(df, 200, 500, 10, seed=2)[:, :, 0].astype(int)
    p_cont = np.mean((big[:, 1:] - big[:, :-1]) % 100 == 1)
    assert p_cont == pytest.approx(0.9, abs=0.02)


def test_pick_rule():
    t = pd.DataFrame({"p_breach20": [0.30, 0.10, 0.105, 0.20], "median_cagr": [0.06, 0.05, 0.055, 0.04]},
                     index=["A", "B", "C", "D"])
    assert pick_rule(t) == "C"
