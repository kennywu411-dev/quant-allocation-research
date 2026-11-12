"""因子线看板（静态网页，ECharts 交互）：python -m quant.alpha.dashboard [--tests N] [--public-tests N] [--site DIR]
→ reports/看板/因子看板.html（私有版，完整）与 reports/看板/因子看板-公开版.html；模板在 quant/alpha/dashboard.html，
图表库 reports/看板/echarts.min.js（ECharts 5.6.0，Apache-2.0）和网页放在一起，不走外网。
数据来自周线缓存的回测、research/alpha_results.json 与 alpha_round2.json（两轮试验及修正前的版本）、
research/alpha_checkup.json（体检）、research/alpha_monitor.json（月度流水线，逐月 RankIC）、research/tsdata_coverage.json（数据层覆盖）、
research/p5_benchmarks.json（ETF 配置线回测指标）。页面上的数字全部从这些文件读，不手写。
公开版由 public_payload 白名单生成：两轮已公开的试验结果、归一化净值与回撤、分年分月超额、逐月 RankIC、体检表、
股票池数量、数据层覆盖、ETF 配置线回测指标和流程；不含持仓、股票代码、持仓只数、观察盘记录、风格暴露、金额、账户市值比例。"""
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.alpha import evaluate as E, round2, shadow, spec
from quant.alpha.registry import REGISTRY
from quant.factors import evaluate as fev

OUT = Path("reports/看板")
TEMPLATE = Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")
ECHARTS = "echarts.min.js"  # ECharts 5.6.0（Apache-2.0），和网页放在同一个目录，不走外网
BENCH = "股票池等权"
PIPELINE = [
    {"title": "数据层", "detail": "全 A 股含退市股的行情与带公告日的财报，本地分片缓存、断点续传；调仓日只用当时已经知道的数据"},
    {"title": "预先登记", "detail": "股票池、因子定义、通过门槛、累计试验次数先提交到版本库，再看结果；没登记的因子拒绝对真实数据出结果"},
    {"title": "因子库与评测", "detail": "写一个函数并登记即可评测：RankIC、分组、换手与成本、纯多头超额、市值中性"},
    {"title": "组合构造", "detail": "涨停买不进、跌停和停牌卖不出、分时期的交易成本、降换手的持仓规则"},
    {"title": "多重检验", "detail": "t 值门槛取 3，并按累计试验次数计算通缩夏普；不为凑显著性调参或追加变体"},
    {"title": "观察盘与监控", "detail": "每月只记账不下单，用之后的真实行情算收益，对比回测偏差并监控因子衰减"},
]


# 页面上用到的术语，第一次出现的地方就地解释；全页只有这一套说法，不按读者分版本
GLOSSARY = [
    {"term": "因子", "plain": "给每只股票打分的一条规则，比如“最近波动越小，分数越高”。"},
    {"term": "超额", "plain": "组合收益减去基准的收益。基准就是把每个月可选的股票（股票池）每只都买一样多。大于 0 才说明挑股票有用。"},
    {"term": "RankIC", "plain": "每个月按因子分数给股票排名，再按下个月的涨跌排名，看两个排名有多像。正数是排对了。股价大部分是随机波动，所以 0.05 就算不错。"},
    {"term": "t 值", "plain": "结果离“纯属运气”有多远。越大越不像巧合（也说越“显著”），这里要求 3 以上。"},
    {"term": "通缩夏普", "plain": "试得越多，越容易碰上一个好看的结果。它把试验次数算进去，给出“这不是运气”的把握，0 到 1 之间，0.59 就是不到六成把握。这里要求 0.95，也就是统计上常用的 95% 把握标准。英文缩写 DSR。"},
    {"term": "回撤", "plain": "从之前的最高点跌下来多少。最大回撤就是最难熬的那一段跌幅。"},
    {"term": "换手", "plain": "每个月换掉多大比例的持仓。换得越多，交易成本越高。"},
    {"term": "样本外", "plain": "定规则时没有用到、留着只做检验的那段历史（这里是后半段）。"},
]


# 每次试验一句白话：这条规则买什么样的股票。写法对照 spec.py 和 library.py 里的登记定义
PLAIN = {
    "LOWVOL": "过去一年涨跌越平稳的股票，分数越高",
    "MOM12_1": "过去一年（跳过最近一个月）涨得越多，分数越高",
    "LOWTURN": "最近四周交易越冷清的股票，分数越高",
    "REV21": "最近四周跌得越多，分数越高（赌它反弹）",
    "SIZE": "公司市值越小，分数越高",
    "IVOL": "扣掉大盘的影响后，自身波动越小，分数越高",
    "ILLIQ": "成交越不活跃、少量资金就能推动价格的股票，分数越高",
    "REV5": "最近一周跌得越多，分数越高（赌它反弹）",
    "REV10": "最近两周跌得越多，分数越高（赌它反弹）",
    "MAX": "最近四周里最大的单周涨幅越小，分数越高（避开暴涨过的）",
    "等权合成": "把 10 个因子的分数直接取平均",
    "IC加权合成": "10 个因子按各自过去的准确程度加权平均",
    "LightGBM合成": "用机器学习模型把 10 个因子合成一个分数",
    "慢因子合成": "只用 4 个不需要频繁换股票的因子取平均",
    "等权合成+缓冲带": "10 因子平均，但排名小幅下滑时先不卖，减少换手",
    "慢因子合成+缓冲带": "4 个慢因子平均，排名小幅下滑时先不卖",
    "等权合成（市值中性）": "10 因子平均，先去掉“公司大小”带来的影响",
    "IVOL（市值中性）": "低特质波动因子，先去掉“公司大小”带来的影响",
    "剔除最差组": "只避开分数最低的五分之一，其余股票都买",
}


def nav_series(r: pd.Series) -> dict:
    """月度收益 → 从 1 开始的归一化净值（第一个点是建仓前一个月末）。"""
    r = r.dropna()
    start = (r.index[0] - pd.offsets.MonthEnd(1)).date()
    return {"dates": [str(start), *[str(d.date()) for d in r.index]], "values": [1.0, *np.cumprod(1 + r.to_numpy()).tolist()]}


def style_exposure(z: dict[str, pd.DataFrame], held: set, t: pd.Timestamp) -> dict:
    """持仓在各因子上的平均标准化值（股票池均值为 0）。"""
    cols = sorted(held)
    return {k: float(v.loc[t, cols].mean()) for k, v in z.items()}


def drawdown(values: list[float]) -> list[float]:
    """净值距离此前最高点的跌幅（0 或负数）。"""
    v = np.asarray(values, dtype=float)
    return (v / np.maximum.accumulate(v) - 1).tolist()


def _num(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def research_summary(r1: dict, r2: dict, o1: dict, o2: dict) -> dict:
    """两轮试验的结果表、通过情况和勘误前后对照。r1/r2 = 修正后的结果文件，o1/o2 = 修正前的。
    第二轮里的“对照”行是第一轮组合的重算，不是新试验，不计入。"""
    def rows(a, b):
        g = lambda v, k: _num(v.get(k))
        out = [{"round": 1, "name": k, "plain": PLAIN.get(k), "rank_ic": _num(v["rank_ic"]), "t": _num(v["t"]), "ex_ann": _num(v["ex_ann"]), "ex_t": None,
                "oos_ex_ann": _num(v["oos_ex_ann"]), "dsr": _num(v.get("dsr")), "passed": bool(v["passed"]),
                "oos_rank_ic": g(v, "oos_rank_ic"), "oos_t": g(v, "oos_t"), "icir": g(v, "icir_ann"), "ex_mdd": g(v, "ex_mdd"),
                "turn": g(v, "top_turn"), "ls_ann": g(v, "ls_ann")} for k, v in a["factors"].items()]
        out += [{"round": 2, "name": k, "plain": PLAIN.get(k), "rank_ic": None, "t": None, "ex_ann": _num(v["ex_ann"]), "ex_t": _num(v["ex_t"]),
                 "oos_ex_ann": _num(v["oos_ex_ann"]), "dsr": _num(v["dsr"]), "passed": bool(v["passed"]),
                 "oos_ex_t": g(v, "oos_ex_t"), "gross_ex_ann": g(v, "gross_ex_ann"), "ex_mdd": g(v, "ex_mdd"), "turn": g(v, "top_turn"),
                 "top_ann_net": g(v, "top_ann_net"), "bench_ann": g(v, "bench_ann")}
                for k, v in b["trials"].items() if "对照" not in k]
        return out
    new, old = rows(r1, r2), rows(o1, o2)
    cnt = lambda t, r: sum(x["passed"] for x in t if x["round"] == r)
    top = lambda t: max(x["dsr"] for x in t if x["dsr"] is not None)
    n_after, n_before = (max(v["n"] for v in x["trials"].values()) for x in (r2, o2))
    for x in new:
        x["shadow"] = bool(x["passed"] and x["dsr"] is not None and x["dsr"] >= spec.R2_DSR_PASS)
    return {"trials": new, "n_trials": len(new), "n_passed": sum(x["passed"] for x in new), "n_shadow": sum(x["shadow"] for x in new),
            "max_dsr": top(new), "dsr_pass": spec.R2_DSR_PASS, "t_pass": spec.R2_T_PASS,
            "rounds": [{"round": r, "n": sum(x["round"] == r for x in new), "passed": cnt(new, r)} for r in (1, 2)],
            # 修正前的月度序列少了被覆盖的持有期，又多记了最后一个收益为 0 的月份：被丢的期数 = 修正后 - (修正前 - 1)
            "erratum": {"periods_before": n_before, "periods_after": n_after, "rebalances": n_after + 1, "dropped": n_after - n_before + 1,
                        "round1_before": cnt(old, 1), "round1_after": cnt(new, 1), "round2_before": cnt(old, 2), "round2_after": cnt(new, 2),
                        "max_dsr_before": top(old), "max_dsr_after": top(new)}}


def monthly_excess(dates: list[str], values: list[float], bench: list[float]) -> list[list]:
    """归一化净值 → 每个月相对基准的超额收益，[年, 月, 超额]；第一个点是起点，没有收益。"""
    v, b = np.asarray(values, dtype=float), np.asarray(bench, dtype=float)
    ex = (v[1:] / v[:-1] - 1) - (b[1:] / b[:-1] - 1)
    return [[int(d[:4]), int(d[5:7]), float(x)] for d, x in zip(dates[1:], ex)]


ETF_FIELDS = ("is_cagr", "oos_cagr", "full_cagr", "mdd_worst", "ann_vol", "sharpe", "calmar_worst")


def etf_summary(bm: dict) -> dict:
    """ETF 配置线：只取 p5_benchmarks.json 里的回测指标（白名单），不带账户市值比例、金额、持仓。"""
    rows = [{"name": k, **{f: _num(v.get(f)) for f in ETF_FIELDS},
             "years": {y: {"ret": _num(d["ret"]), "mdd": _num(d["mdd"])} for y, d in v.get("years", {}).items()}}
            for k, v in bm.items() if isinstance(v, dict)]
    window = next((v["window"] for v in bm.values() if isinstance(v, dict) and "window" in v), None)
    return {"window": window, "basis": bm.get("口径"), "report": bm.get("report"), "rows": rows}


def enrich(p: dict, r1: dict, r2: dict, o1: dict, o2: dict, coverage: dict | None, tests: int | None, etf: dict | None = None) -> dict:
    """给看板数据加上两轮结果、回撤、分年与分月超额、数据层覆盖、ETF 配置线回测和测试数。"""
    s = p["nav"]["series"]
    if BENCH in s:
        p["monthly"] = {k: monthly_excess(p["nav"]["dates"], v, s[BENCH]) for k, v in s.items() if k != BENCH}
    if etf:
        p["etf"] = etf_summary(etf)
    p["research"] = research_summary(r1, r2, o1, o2)
    p["drawdown"] = {k: drawdown(v) for k, v in p["nav"]["series"].items()}
    p["yearly"] = {k: r2["trials"][k]["by_year"] for k in p["nav"]["series"] if k in r2["trials"]}
    p["meta"]["n_codes"] = r1.get("n_codes")
    if coverage:
        p["coverage"] = coverage
    if tests:
        p["tests"] = int(tests)
    return p


def build_payload(b: dict, monitor: dict, checkup: dict) -> dict:
    fwd, univ = b["fwd"], b["univ"]
    last = [t for t in b["rb"] if fwd.loc[t].notna().any()]  # 下期收益还没走完的调仓日不进净值
    z = {k: E.zscores(v, univ) for k, v in b["f"].items()}
    sig = {"等权合成+缓冲带": E.equal_weighted(z), "慢因子合成+缓冲带": E.equal_weighted({k: z[k] for k in spec.R2_SLOW})}
    tg = {k: round2.buffered_sets(v, univ) for k, v in sig.items()}
    series, dates = {}, None
    for k in shadow.TRACKED:
        sim = E.simulate({t: s for t, s in tg[k].items() if t in last}, fwd, b["up"], b["dn"], b["tradable"])
        nv = nav_series(sim.net.astype(float))
        series[k], dates = nv["values"], nv["dates"]
        idx = sim.index
    bench = pd.Series({fev.hold_label(t): float(fwd.loc[t, univ.loc[t]].fillna(0).mean()) for t in last}).reindex(idx)
    series[BENCH] = nav_series(bench)["values"]
    ic = {}
    for k, d in monitor.get("ic_series", {}).items():
        s = pd.Series(d)
        ic[k] = {"dates": list(s.index), "ic": s.tolist(), "roll": [None if pd.isna(x) else float(x) for x in s.rolling(12).mean()]}
    table = []
    for k, c in checkup.items():
        n = c["size_neutral"]
        table.append({"name": k, "rank_ic": c["ic"]["rank_ic"], "t": c["ic"]["t"], "oos_rank_ic": c["ic"]["oos_rank_ic"],
                      "ex_ann": c["long_only"]["ex_ann"], "ex_t": c["long_only"]["ex_t"], "oos_ex_ann": c["long_only"]["oos_ex_ann"],
                      "turn": c["long_only"]["top_turn"], "groups": c["groups"]["ann"], "monotonic": bool(c["groups"]["monotonic"]),
                      "cost_drag": c["cost"]["cost_drag_ann"], "gross_ex_ann": c["long_only"]["gross_ex_ann"], "icir": c["ic"]["icir_ann"],
                      "win": c["ic"]["win"], "desc": REGISTRY[k].desc if k in REGISTRY else None, "plain": PLAIN.get(k),
                      "neutral_ex_ann": None if isinstance(n, str) else n["long_only"]["ex_ann"], "passed": c["round1"]["passed"]})
    t_last = b["rb"][-1]
    style = {k: style_exposure(z, tg[k][t_last], t_last) for k in shadow.TRACKED}
    return {"meta": {"asof": f"{date.today():%Y-%m-%d}", "start": dates[0], "end": dates[-1], "n_trials": spec.R2_N_TRIALS,
                     "style_date": str(t_last.date()), "rebalance": monitor.get("rebalance"),
                     "split": str(spec.SPLIT)[:10], "pipeline_run": monitor.get("asof"),
                     "data_last": monitor.get("data", {}).get("last_day"), "source": monitor.get("data", {}).get("source")},
            "universe": {"dates": [str(t.date()) for t in univ.index], "n": [int(x) for x in univ.sum(axis=1)]},
            "nav": {"dates": dates, "series": series}, "ic": ic, "table": table, "style": style,
            "shadow": {k: monitor.get(k) for k in ("holdings", "realized", "deviation", "ic_alerts", "stale_days", "data")}}


PUBLIC_KEYS = ("nav", "drawdown", "yearly", "research", "coverage", "ic", "table", "universe", "monthly", "etf")
PUBLIC_META = ("asof", "start", "end", "n_trials", "n_codes", "pipeline_run", "data_last", "source", "split")


def public_payload(p: dict, tests: int | None = None) -> dict:
    """白名单：已公开的两轮试验结果、归一化净值与回撤、分年超额、数据层覆盖、流程和少量元信息。
    tests = 公开仓库自己的测试数（和私有仓库不同，所以单独给；不给就不显示）。"""
    out = {"meta": {k: p["meta"][k] for k in PUBLIC_META if k in p["meta"]}, "pipeline": PIPELINE, "glossary": GLOSSARY}
    out.update({k: p[k] for k in PUBLIC_KEYS if k in p})
    if tests:
        out["tests"] = int(tests)
    return out


def _clean(o):
    """NaN / inf 写成 null：浏览器的 JSON.parse 不认 NaN。"""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not math.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def render(p: dict, public: bool, echarts: str = ECHARTS) -> str:
    p = {**p, "glossary": GLOSSARY}
    data = json.dumps(_clean(p), ensure_ascii=False, default=float).replace("</", "<\\/")
    return (TEMPLATE.replace("__TITLE__", "A 股选股因子研究看板" if public else "A 股选股因子研究看板（私有版）")
            .replace("__ECHARTS__", echarts).replace("__PUBLIC__", "true" if public else "false").replace("__DATA__", data))


def main(argv: list[str] | None = None) -> int:
    import argparse
    import warnings
    warnings.filterwarnings("ignore")
    from quant.alpha.weekly import build
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", type=int, default=None, help="本仓库 pytest 通过的测试数（照实际输出填）")
    ap.add_argument("--public-tests", type=int, default=None, help="公开仓库 pytest 通过的测试数")
    ap.add_argument("--site", default=None, help="再写一份公开版到这个目录的 index.html（给 GitHub Pages 短网址用）")
    ap.add_argument("--site-echarts", default="../reports/%E7%9C%8B%E6%9D%BF/echarts.min.js", help="--site 那份网页里 ECharts 的相对路径")
    a = ap.parse_args(argv)
    load = lambda f: json.loads(Path("research", f).read_text())
    cov = Path("research/tsdata_coverage.json")
    p = build_payload(build(), load("alpha_monitor.json"), load("alpha_checkup.json"))
    enrich(p, load("alpha_results.json"), load("alpha_round2.json"), load("alpha_results-修正前丢月.json"), load("alpha_round2-修正前丢月.json"),
           json.loads(cov.read_text()) if cov.exists() else None, a.tests, load("p5_benchmarks.json"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "因子看板.html").write_text(render(p, public=False))
    pub = public_payload(p, a.public_tests)
    (OUT / "因子看板-公开版.html").write_text(render(pub, public=True))
    if a.site:
        Path(a.site).mkdir(parents=True, exist_ok=True)
        (Path(a.site) / "index.html").write_text(render(pub, public=True, echarts=a.site_echarts))
    print(f"净值 {p['meta']['start']} 至 {p['meta']['end']}，{len(p['nav']['dates'])} 个点 → {OUT}/因子看板.html、因子看板-公开版.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
