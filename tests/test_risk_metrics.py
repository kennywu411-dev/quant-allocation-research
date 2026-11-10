import pandas as pd

from quant.research.risk_metrics import summarize


def test_summarize_worst_mode_drawdown_and_keys():
    idx = pd.bdate_range("2018-01-01", "2021-12-31")
    end = pd.Series(1.0, index=idx).cumsum() / len(idx) + 1
    mid = end.copy()
    mid.iloc[300] = mid.iloc[299] * 0.7  # 月中调仓口径有一次 -30% 的回撤
    rf = pd.Series(1.0, index=idx)
    s = summarize({"end": end, "mid": mid, "start": end}, rf)
    assert abs(s["mdd_worst"] - (-0.3)) < 1e-9
    assert s["mdd_end"] > -1e-12 and s["calmar_end"] == float("inf")
    assert abs(s["calmar_worst"] - s["full_cagr"] / 0.3) < 1e-9
    assert {"is_cagr", "oos_cagr", "ann_vol", "sharpe", "window"} <= set(s)


def test_p5_w_us_from_trials(tmp_path):
    import pytest
    from quant.research.risk_metrics import p5_w_us
    f = tmp_path / "t.csv"
    f.write_text("name,w_us\nP5核心合并,0.4\n其他,0.9\nP5核心合并,0.45\n")
    assert p5_w_us(f) == 0.45
    f.write_text("name\nP5核心合并\n")
    with pytest.raises(SystemExit):
        p5_w_us(f)
