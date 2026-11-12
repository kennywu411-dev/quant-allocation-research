"""看板：归一化净值、风格暴露、公开版脱敏、单文件 HTML。"""
import json
import re

import numpy as np
import pandas as pd
import pytest

from quant.alpha import spec


def test_nav_is_normalized_to_one_at_start():
    from quant.alpha import dashboard as D
    idx = pd.date_range("2024-01-31", periods=3, freq="ME")
    nav = D.nav_series(pd.Series([0.10, -0.50, 0.20], index=idx))
    assert nav["values"] == pytest.approx([1.0, 1.10, 0.55, 0.66])
    assert len(nav["dates"]) == 4 and nav["dates"][1] == "2024-01-31"


def test_style_exposure_is_mean_zscore_of_holdings():
    from quant.alpha import dashboard as D
    t = pd.Timestamp("2024-01-31")
    z = {"SIZE": pd.DataFrame({"A": [1.0], "B": [-1.0], "C": [np.nan]}, index=[t]),
         "IVOL": pd.DataFrame({"A": [0.5], "B": [0.5], "C": [2.0]}, index=[t])}
    e = D.style_exposure(z, {"A", "C"}, t)
    assert e == {"SIZE": pytest.approx(1.0), "IVOL": pytest.approx(1.25)}


def _private():
    return {"meta": {"asof": "2026-11-12", "rebalance": "2026-10-30", "n_trials": 19, "start": "2014-01-31", "end": "2026-09-25"},
            "nav": {"dates": ["2014-01-31", "2014-02-28"],
                    "series": {"等权合成+缓冲带": [1.0, 1.02], "慢因子合成+缓冲带": [1.0, 1.01], "股票池等权": [1.0, 1.0]}},
            "ic": {"IVOL": {"dates": ["2014-02-28"], "ic": [0.09], "roll": [None]}},
            "table": [{"name": "IVOL", "rank_ic": 0.09, "t": 8.0, "groups": [0.01, 0.02, 0.03, 0.04, 0.05], "passed": True}],
            "style": {"等权合成+缓冲带": {"IVOL": 0.8}},
            "shadow": {"holdings": {"等权合成+缓冲带": {"target_n": 718, "held_n": 700, "overlap": None}}, "realized": [], "deviation": [],
                       "ic_alerts": {"IVOL": {"full": 0.09, "recent": 0.05, "alert": False}}},
            "codes_sample": ["sz.000001"]}


def test_public_payload_keeps_only_normalized_nav_and_process():
    from quant.alpha import dashboard as D
    pub = D.public_payload(_private())
    assert set(pub) == {"meta", "nav", "pipeline"}
    text = json.dumps(pub, ensure_ascii=False)
    assert not re.search(r"(sh|sz|bj)\.\d{6}", text)
    assert not any(k in text for k in spec.W_FACTORS)  # 不出现因子名
    assert "缓冲带" not in text and "718" not in text  # 不出现持仓构造名和持仓只数
    assert all(v[0] == 1.0 for v in pub["nav"]["series"].values()) and len(pub["nav"]["series"]) == 3


def test_render_is_a_single_self_contained_html_file():
    from quant.alpha import dashboard as D
    for public in (False, True):
        p = D.public_payload(_private()) if public else _private()
        html = D.render(p, public=public)
        assert html.lstrip().startswith("<!doctype html>") and "</html>" in html
        assert not re.search(r'(src|href)\s*=\s*["\']https?://', html)  # 不依赖外部资源
        assert "不是投资建议" in html
        data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1))
        assert data["nav"]["series"].keys() == p["nav"]["series"].keys()


def test_public_render_contains_no_private_fields():
    from quant.alpha import dashboard as D
    html = D.render(D.public_payload(_private()), public=True)
    assert "IVOL" not in html and "sz.000001" not in html and "缓冲带" not in html
