"""第三轮（GRU 序列模型）：特征不偷看未来、窗口形状、合成数据上学得到信号、结果可复现。"""
import importlib.util
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from quant.alpha import round3, spec

needs_torch = pytest.mark.skipif(importlib.util.find_spec("torch") is None, reason="没装 torch")


def _in_subprocess(code: str) -> None:
    """macOS 上 PyTorch 和 LightGBM 的 OpenMP 在同一进程里会冲突，用到 torch 的断言放到子进程里跑。"""
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]


def _weekly(n_weeks=140, n_codes=120, seed=0):
    rng = np.random.default_rng(seed)
    weeks = pd.date_range("2015-01-02", periods=n_weeks, freq="W-FRI")
    codes = [f"sz.{i:06d}" for i in range(n_codes)]
    ret = pd.DataFrame(rng.normal(0, 0.04, (n_weeks, n_codes)), index=weeks, columns=codes)
    turn = pd.DataFrame(rng.uniform(0.5, 5, (n_weeks, n_codes)), index=weeks, columns=codes)
    amount = pd.DataFrame(rng.uniform(1e7, 1e9, (n_weeks, n_codes)), index=weeks, columns=codes)
    traded = pd.DataFrame(True, index=weeks, columns=codes)
    traded.iloc[10:14, 3] = False
    return {"ret": ret.where(traded), "turn": turn, "amount": amount, "traded": traded, "close": ret}


def test_channels_centered_and_untraded_zero():
    w = _weekly()
    X, valid = round3.channels(w)
    assert X.shape == (140, 120, 3) and X.dtype == np.float32
    assert (X[10:14, 3] == 0).all() and not valid[10:14, 3].any()
    assert X.min() > -0.5 and X.max() <= 0.5


def test_channels_do_not_look_ahead():
    w = _weekly()
    X0, _ = round3.channels(w)
    w2 = {k: v.copy() for k, v in w.items()}
    for k in ("ret", "turn", "amount"):
        w2[k].iloc[80:] = w2[k].iloc[80:].to_numpy()[:, ::-1]  # 改掉第 80 周以后的全部数据
    X1, _ = round3.channels(w2)
    assert np.array_equal(X0[:80], X1[:80])
    seq0, _ = round3.windows(X0, np.ones(X0.shape[:2], bool), 79, np.arange(120))
    seq1, _ = round3.windows(X1, np.ones(X1.shape[:2], bool), 79, np.arange(120))
    assert np.array_equal(seq0, seq1)


def test_windows_shape_order_and_padding():
    w = _weekly()
    X, valid = round3.channels(w)
    seq, n = round3.windows(X, valid, 100, np.array([0, 3]))
    assert seq.shape == (2, spec.R3_LOOKBACK, 3)
    assert np.array_equal(seq[0, -1], X[100, 0]) and np.array_equal(seq[0, 0], X[100 - spec.R3_LOOKBACK + 1, 0])
    seq, n = round3.windows(X, valid, 20, np.array([0, 3]))
    assert seq.shape == (2, spec.R3_LOOKBACK, 3) and (seq[:, :spec.R3_LOOKBACK - 21] == 0).all()
    assert n[0] == 21 and n[1] == 17  # 第 3 只有 4 周没成交


@needs_torch
def test_fit_predict_learns_planted_signal_and_is_reproducible():
    _in_subprocess("""
import numpy as np, pandas as pd
from quant.alpha import round3, spec
rng = np.random.default_rng(1)
X = rng.uniform(-0.5, 0.5, (6000, spec.R3_LOOKBACK, 3)).astype(np.float32)
y = (X[:, -4:, 0].mean(axis=1) + rng.normal(0, 0.05, 6000)).astype(np.float32)  # 目标 = 最近 4 周收益通道的均值
p1 = round3.fit_predict(X[:5000], y[:5000], [X[5000:]], epochs=4)[0]
p2 = round3.fit_predict(X[:5000], y[:5000], [X[5000:]], epochs=4)[0]
assert np.allclose(p1, p2)
assert pd.Series(p1).corr(pd.Series(y[5000:]), method="spearman") > 0.5
""")


@needs_torch
def test_gru_composite_only_predicts_inside_universe_after_enough_history():
    _in_subprocess("""
import numpy as np, pandas as pd
from quant.alpha import round3
from quant.alpha.weekly import rebalance_dates
from tests.test_alpha_round3 import _weekly
w = _weekly(n_weeks=190)
rb = rebalance_dates(w["close"].index)[:-1]
fwd = pd.DataFrame(np.random.default_rng(2).normal(0, 0.05, (len(rb), 120)), index=rb, columns=w["close"].columns)
univ = pd.DataFrame(True, index=rb, columns=w["close"].columns)
univ.iloc[:, :10] = False
pred = round3.gru_composite(w, rb, fwd, univ, epochs=1)
has = pred.notna().any(axis=1)
first = has[has].index[0]
assert first.month == 12 and rb.get_loc(first) >= 24
assert pred.iloc[:, :10].isna().all().all()
assert pred.loc[first].iloc[10:].notna().all()
""")
