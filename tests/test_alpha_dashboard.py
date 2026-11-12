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


def _f(passed, dsr, ex=0.01, n=152):
    return {"rank_ic": 0.05, "t": 4.0, "oos_rank_ic": 0.04, "ex_ann": ex, "oos_ex_ann": ex / 2, "passed": passed, "dsr": dsr, "n": n,
            "top_turn": 0.5}


def _t(passed, dsr, n=152):
    return {"ex_ann": 0.05, "ex_t": 3.1 if passed else 2.0, "oos_ex_ann": 0.04, "passed": passed, "dsr": dsr, "shadow": False, "n": n,
            "top_turn": 0.1, "n_hold": 525.3, "by_year": {"2014": 0.1, "2015": -0.02}}


def _results(n_pass1, n_pass2, dsr, n):
    r1 = {"factors": {f"F{i}": _f(i < n_pass1, dsr if i == 0 else float("nan")) for i in range(13)}}
    r2 = {"n_trials": 19, "trials": {**{f"T{i}": _t(i < n_pass2, dsr / 2, n) for i in range(6)}, "等权合成（第一轮，对照）": _t(False, 0.06, n)}}
    return r1, r2


def test_research_summary_lists_19_trials_and_round_counts():
    from quant.alpha import dashboard as D
    r1, r2 = _results(7, 1, 0.59, 152)
    o1, o2 = _results(4, 0, 0.50, 134)
    s = D.research_summary(r1, r2, o1, o2)
    assert len(s["trials"]) == 19 and not any("对照" in t["name"] for t in s["trials"])  # 对照组不是新试验
    assert [(r["n"], r["passed"]) for r in s["rounds"]] == [(13, 7), (6, 1)]
    assert s["n_trials"] == 19 and s["n_passed"] == 8 and s["n_shadow"] == 0 and s["max_dsr"] == pytest.approx(0.59)
    t0 = s["trials"][0]
    assert t0["round"] == 1 and t0["rank_ic"] == 0.05 and t0["ex_t"] is None  # 第一轮没有超额 t
    assert s["trials"][1]["dsr"] is None  # NaN 写成 null，网页里不会出现 NaN
    assert s["trials"][13]["round"] == 2 and s["trials"][13]["ex_t"] == pytest.approx(3.1) and "n_hold" not in s["trials"][13]
    e = s["erratum"]
    assert (e["periods_before"], e["periods_after"], e["rebalances"], e["dropped"]) == (134, 152, 153, 19)
    assert (e["round1_before"], e["round1_after"], e["round2_before"], e["round2_after"]) == (4, 7, 0, 1)
    assert e["max_dsr_before"] == pytest.approx(0.50) and e["max_dsr_after"] == pytest.approx(0.59)


def test_drawdown_is_distance_from_running_peak():
    from quant.alpha import dashboard as D
    assert D.drawdown([1.0, 1.2, 0.9, 1.5, 1.2]) == pytest.approx([0.0, 0.0, -0.25, 0.0, -0.2])


def _full_private():
    from quant.alpha import dashboard as D
    p = _private()
    r1, r2 = _results(7, 1, 0.59, 152)
    p["research"] = D.research_summary(r1, r2, *_results(4, 0, 0.50, 134))
    p["drawdown"] = {k: D.drawdown(v) for k, v in p["nav"]["series"].items()}
    p["yearly"] = {"慢因子合成+缓冲带": {"2014": 0.1, "2015": -0.02}}
    p["coverage"] = {"asof": "2026-11-12", "total_rows": 100, "datasets": [{"name": "daily", "label": "日线行情", "rows": 100, "first": "20100104", "last": "20261111"}]}
    p["tests"] = 280
    return p


def test_public_payload_is_a_whitelist_without_holdings_or_codes():
    from quant.alpha import dashboard as D
    pub = D.public_payload(_full_private(), tests=250)
    assert set(pub) == {"meta", "nav", "drawdown", "yearly", "research", "coverage", "pipeline", "tests", "ic", "table", "glossary"}
    assert pub["tests"] == 250  # 公开仓库的测试数另外给，不沿用私有仓库的
    text = json.dumps(pub, ensure_ascii=False)
    assert not re.search(r"(sh|sz|bj)\.\d{6}", text)
    assert "718" not in text and "525.3" not in text and "n_hold" not in text  # 不出现持仓只数
    assert "ic_alerts" not in text and "target_n" not in text and "style" not in pub and "shadow" not in pub  # 观察盘持仓、风格暴露不公开
    assert "rebalance" not in pub["meta"]
    assert all(v[0] == 1.0 for v in pub["nav"]["series"].values()) and len(pub["nav"]["series"]) == 3
    assert "tests" not in D.public_payload(_full_private())  # 没给公开仓库测试数就不显示


def test_render_is_a_single_self_contained_html_file():
    from quant.alpha import dashboard as D
    for public in (False, True):
        p = D.public_payload(_full_private(), tests=250) if public else _full_private()
        html = D.render(p, public=public)
        assert html.lstrip().startswith("<!doctype html>") and "</html>" in html
        assert not re.search(r'(src|href)\s*=\s*["\']https?://', html)  # 不依赖外部资源
        assert "不是投资建议" in html
        data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1))
        assert data["nav"]["series"].keys() == p["nav"]["series"].keys()
        assert "—" not in D.TEMPLATE and "–" not in D.TEMPLATE and "NaN" not in html


def test_public_render_contains_no_private_fields():
    from quant.alpha import dashboard as D
    html = D.render(D.public_payload(_full_private(), tests=250), public=True)
    data = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1)  # 模板里的私有版代码不算，只看数据
    assert "sz.000001" not in html and "718" not in data and "target_n" not in data and "ic_alerts" not in data


def test_monthly_excess_is_portfolio_minus_benchmark_by_calendar_month():
    from quant.alpha import dashboard as D
    m = D.monthly_excess(["2014-01-31", "2014-02-28", "2014-03-28"], [1.0, 1.10, 1.21], [1.0, 1.05, 1.05])
    assert [(y, mo) for y, mo, _ in m] == [(2014, 2), (2014, 3)]  # 第一个点是起点，没有收益
    assert [x for *_, x in m] == pytest.approx([0.05, 0.10])


def test_etf_summary_keeps_only_whitelisted_metrics():
    from quant.alpha import dashboard as D
    row = {"window": "2007-06-01 至 2026-10-30", "is_cagr": 0.05, "oos_cagr": 0.06, "full_cagr": 0.055, "mdd_worst": -0.14, "mdd_end": -0.12,
           "ann_vol": 0.08, "sharpe": 0.38, "calmar_worst": 0.41, "w_us": 0.51, "years": {"2008": {"ret": 0.02, "mdd": -0.1}}}
    e = D.etf_summary({"口径": "说明", "report": "reports/x.md", "方案": row, "基准": dict(row, full_cagr=0.07)})
    assert [r["name"] for r in e["rows"]] == ["方案", "基准"] and e["window"] == "2007-06-01 至 2026-10-30" and e["basis"] == "说明"
    assert e["rows"][1]["full_cagr"] == 0.07 and e["rows"][0]["years"]["2008"] == {"ret": 0.02, "mdd": -0.1}
    assert "w_us" not in json.dumps(e)  # 账户市值比例不进看板


def test_research_summary_carries_detail_fields_but_no_holding_counts():
    from quant.alpha import dashboard as D
    s = D.research_summary(*_results(7, 1, 0.59, 152), *_results(4, 0, 0.50, 134))
    assert s["trials"][0]["oos_rank_ic"] == 0.04 and s["trials"][0]["turn"] == 0.5
    assert s["trials"][13]["turn"] == 0.1 and "n_hold" not in json.dumps(s)


def test_render_points_at_a_local_echarts_file():
    from quant.alpha import dashboard as D
    html = D.render(_full_private(), public=False, echarts="../x/echarts.min.js")
    assert '<script src="../x/echarts.min.js"></script>' in html
    assert '<script src="echarts.min.js"></script>' in D.render(_full_private(), public=False)


def test_public_payload_adds_etf_universe_and_monthly_when_present():
    from quant.alpha import dashboard as D
    p = _full_private()
    p["etf"], p["universe"], p["monthly"] = {"rows": []}, {"dates": ["2014-01-31"], "n": [1500]}, {"x": [[2014, 2, 0.01]]}
    p["meta"].update(generated="2026-11-12 20:00", data_last="2026-11-11", source="tushare", pipeline_run="2026-11-12")
    pub = D.public_payload(p)
    assert {"etf", "universe", "monthly"} <= set(pub)
    assert pub["meta"]["data_last"] == "2026-11-11"
    assert "generated" not in pub["meta"]  # 页面不显示生成时间，只保留“数据截至”
    assert "页面生成" not in D.TEMPLATE and "generated" not in D.TEMPLATE
    assert "20:00" not in D.render(pub, public=True)


def test_glossary_explains_every_term_the_page_uses_in_plain_words():
    from quant.alpha import dashboard as D
    terms = [g["term"] for g in D.GLOSSARY]
    assert {"因子", "超额", "RankIC", "t 值", "通缩夏普", "回撤", "换手", "样本外"} <= set(terms)
    assert all(len(g["plain"]) >= 12 and "—" not in g["plain"] for g in D.GLOSSARY)
    pub = D.public_payload(_full_private())
    assert pub["glossary"] == D.GLOSSARY  # 同一套解释，不按读者分版本
    html = D.render(pub, public=True)
    assert "简明" not in html and "专业模式" not in html
    assert 'id="glossary"' not in html  # 术语不集中放在开头，跟着第一次用到它的图走
    for t in terms:
        assert f'gl("{t}")' in D.TEMPLATE, t


def test_fonts_ship_with_the_page_and_follow_the_echarts_folder():
    from quant.alpha import dashboard as D
    for f in ("Geist.woff", "GeistMono.woff", "OFL.txt"):
        assert (D.OUT / "fonts" / f).exists(), f  # 字体和许可证随仓库托管，不走外网
    html = D.render(_full_private(), public=False)
    assert 'url("fonts/Geist.woff")' in html and 'url("fonts/GeistMono.woff")' in html
    site = D.render(_full_private(), public=False, echarts="../reports/x/echarts.min.js")
    assert 'url("../reports/x/fonts/Geist.woff")' in site  # 短网址那份页面的字体路径跟着图表库走


def test_second_screen_ranks_all_trials_by_name_against_the_threshold():
    from quant.alpha import dashboard as D
    html = D.render(D.public_payload(_full_private()), public=True)
    assert 'id="rank"' in html and 'id="trials"' not in html  # 19 根柱子的图取代原来的试验清单


def test_first_screen_is_headline_plus_one_data_driven_visual():
    from quant.alpha import dashboard as D
    html = D.render(D.public_payload(_full_private()), public=True)
    assert 'id="sieve"' in html and 'id="replay"' in html  # 19 → 8 → 0 的筛选主画面，可重播
    assert 'id="strip"' not in html and 'id="steps"' not in html  # 和主画面重复的数字块、单独的三步做法块都不再占首屏
    assert "prefers-reduced-motion" in html


def test_every_registered_trial_has_a_plain_one_line_description():
    from quant.alpha import dashboard as D
    names = set(spec.W_FACTORS) | set(spec.COMPOSITES) | set(spec.R2_TRIALS)  # 周线版实际检验的 10 个因子
    missing = sorted(n for n in names if n not in D.PLAIN and "对照" not in n)
    assert not missing, missing
    r1, r2 = _results(7, 1, 0.59, 152)
    r1["factors"]["IVOL"] = r1["factors"].pop("F0")
    s = D.research_summary(r1, r2, *_results(4, 0, 0.50, 134))
    assert next(t for t in s["trials"] if t["name"] == "IVOL")["plain"] == D.PLAIN["IVOL"]
    assert s["trials"][0]["plain"] is None  # 没有白话说明的名字不编


def test_front_page_leads_with_what_was_built_and_keeps_the_caveat_in_the_results():
    from quant.alpha import dashboard as D
    t = D.TEMPLATE
    assert "种靠得住" not in t and 'class="n z"' not in t  # 首页不拿“0 种”当标题和主画面的落点
    assert 'id="facts"' in t  # 首屏是属实的正面事实：股票数、年份、数据量、试验数、通过门槛数、测试数
    assert "未达到影子盘候选标准" in t and "不是投资建议" in t  # 诚实的结论还在，放在试验结果和净值图旁
    assert "稳定赚钱" not in t and "稳赚" not in t
