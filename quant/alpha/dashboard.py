"""因子线看板（单文件静态网页）：python -m quant.alpha.dashboard [--tests N] [--public-tests N]
→ reports/看板/因子看板.html（私有版，完整）与 reports/看板/因子看板-公开版.html。
数据来自周线缓存的回测、research/alpha_results.json 与 alpha_round2.json（两轮试验及修正前的版本）、
research/alpha_checkup.json（体检）、research/alpha_monitor.json（月度流水线）、research/tsdata_coverage.json（数据层覆盖）。
页面上的数字全部从这些文件读，不手写。公开版由 public_payload 白名单生成：两轮已公开的试验结果、归一化净值与回撤、
数据层覆盖和流程；不含持仓、股票代码、持仓只数、观察盘记录、风格暴露、金额。"""
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.alpha import evaluate as E, round2, shadow, spec
from quant.factors import evaluate as fev

OUT = Path("reports/看板")
BENCH = "股票池等权"
PIPELINE = [
    {"title": "数据层", "detail": "全 A 股含退市股的行情与带公告日的财报，本地分片缓存、断点续传；调仓日只用当时已经知道的数据"},
    {"title": "预先登记", "detail": "股票池、因子定义、通过门槛、累计试验次数先提交到版本库，再看结果；没登记的因子拒绝对真实数据出结果"},
    {"title": "因子库与评测", "detail": "写一个函数并登记即可评测：RankIC、分组、换手与成本、纯多头超额、市值中性"},
    {"title": "组合构造", "detail": "涨停买不进、跌停和停牌卖不出、分时期的交易成本、降换手的持仓规则"},
    {"title": "多重检验", "detail": "t 值门槛取 3，并按累计试验次数计算通缩夏普；不为凑显著性调参或追加变体"},
    {"title": "观察盘与监控", "detail": "每月只记账不下单，用之后的真实行情算收益，对比回测偏差并监控因子衰减"},
]


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
        out = [{"round": 1, "name": k, "rank_ic": _num(v["rank_ic"]), "t": _num(v["t"]), "ex_ann": _num(v["ex_ann"]), "ex_t": None,
                "oos_ex_ann": _num(v["oos_ex_ann"]), "dsr": _num(v.get("dsr")), "passed": bool(v["passed"])} for k, v in a["factors"].items()]
        out += [{"round": 2, "name": k, "rank_ic": None, "t": None, "ex_ann": _num(v["ex_ann"]), "ex_t": _num(v["ex_t"]),
                 "oos_ex_ann": _num(v["oos_ex_ann"]), "dsr": _num(v["dsr"]), "passed": bool(v["passed"])}
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


def enrich(p: dict, r1: dict, r2: dict, o1: dict, o2: dict, coverage: dict | None, tests: int | None) -> dict:
    """给看板数据加上两轮结果、回撤、分年超额、数据层覆盖和测试数。"""
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
                      "turn": c["long_only"]["top_turn"], "groups": c["groups"]["ann"],
                      "neutral_ex_ann": None if isinstance(n, str) else n["long_only"]["ex_ann"], "passed": c["round1"]["passed"]})
    t_last = b["rb"][-1]
    style = {k: style_exposure(z, tg[k][t_last], t_last) for k in shadow.TRACKED}
    return {"meta": {"asof": f"{date.today():%Y-%m-%d}", "start": dates[0], "end": dates[-1], "n_trials": spec.R2_N_TRIALS,
                     "style_date": str(t_last.date()), "rebalance": monitor.get("rebalance")},
            "nav": {"dates": dates, "series": series}, "ic": ic, "table": table, "style": style,
            "shadow": {k: monitor.get(k) for k in ("holdings", "realized", "deviation", "ic_alerts", "stale_days", "data")}}


PUBLIC_KEYS = ("nav", "drawdown", "yearly", "research", "coverage")


def public_payload(p: dict, tests: int | None = None) -> dict:
    """白名单：已公开的两轮试验结果、归一化净值与回撤、分年超额、数据层覆盖、流程和少量元信息。
    tests = 公开仓库自己的测试数（和私有仓库不同，所以单独给；不给就不显示）。"""
    out = {"meta": {k: p["meta"][k] for k in ("asof", "start", "end", "n_trials", "n_codes") if k in p["meta"]}, "pipeline": PIPELINE}
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


def render(p: dict, public: bool) -> str:
    data = json.dumps(_clean(p), ensure_ascii=False, default=float).replace("</", "<\\/")
    return (TEMPLATE.replace("__TITLE__", "A 股选股因子研究看板" if public else "A 股选股因子研究看板（私有版）")
            .replace("__PUBLIC__", "true" if public else "false").replace("__DATA__", data))


def main(argv: list[str] | None = None) -> int:
    import argparse
    import warnings
    warnings.filterwarnings("ignore")
    from quant.alpha.weekly import build
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", type=int, default=None, help="本仓库 pytest 通过的测试数（照实际输出填）")
    ap.add_argument("--public-tests", type=int, default=None, help="公开仓库 pytest 通过的测试数")
    a = ap.parse_args(argv)
    load = lambda f: json.loads(Path("research", f).read_text())
    cov = Path("research/tsdata_coverage.json")
    p = build_payload(build(), load("alpha_monitor.json"), load("alpha_checkup.json"))
    enrich(p, load("alpha_results.json"), load("alpha_round2.json"), load("alpha_results-修正前丢月.json"), load("alpha_round2-修正前丢月.json"),
           json.loads(cov.read_text()) if cov.exists() else None, a.tests)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "因子看板.html").write_text(render(p, public=False))
    (OUT / "因子看板-公开版.html").write_text(render(public_payload(p, a.public_tests), public=True))
    print(f"净值 {p['meta']['start']} 至 {p['meta']['end']}，{len(p['nav']['dates'])} 个点 → {OUT}/因子看板.html、因子看板-公开版.html")
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--page:#f5f6f7;--surface:#fdfdfd;--ink:#14171a;--ink2:#4b5259;--muted:#737b83;--grid:#e2e5e8;--axis:#c3c8cd;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--warn:#c23a3a;--r:6px}
@media (prefers-color-scheme:dark){:root{--page:#0f1113;--surface:#171a1d;--ink:#eceef0;--ink2:#b4bac0;--muted:#8b9299;--grid:#272b30;--axis:#3b4046;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--warn:#e66767}}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.65 "SF Pro Text",-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Noto Sans SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}
main{max-width:1160px;margin:0 auto;padding:44px 24px 64px}
h1{font-size:34px;line-height:1.25;letter-spacing:-.01em;margin:0 0 14px;font-weight:700;text-wrap:balance}
h2{font-size:21px;line-height:1.3;margin:0 0 6px;font-weight:650}
h1 span{display:block}h3{font-size:14px;margin:0 0 8px;font-weight:600;color:var(--ink2)}
p{margin:0}.num{font-variant-numeric:tabular-nums}
.lead{color:var(--ink2);font-size:16px;max-width:36em}
.sub{color:var(--ink2);font-size:14px;max-width:52em;margin-bottom:18px}
.note{color:var(--muted);font-size:12.5px;margin-top:12px;max-width:60em}
.hero{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,.8fr);gap:48px;align-items:start}
.tag[hidden]{display:none}.tag{display:inline-block;font-size:12px;color:var(--ink2);border:1px solid var(--axis);border-radius:var(--r);padding:1px 8px;margin-bottom:12px}
.funnel{display:grid;gap:16px;padding-top:6px}
.frow{display:grid;grid-template-columns:64px minmax(0,1fr);column-gap:14px;align-items:center}
.frow b{font-size:38px;line-height:1;font-weight:700;font-variant-numeric:tabular-nums;text-align:right}
.frow span{display:block;font-size:13.5px;color:var(--ink2);margin-bottom:6px}
.frow i{display:block;height:10px;border-radius:0 4px 4px 0;background:var(--s1);min-width:2px}
.frow.zero b{color:var(--muted)}.frow.zero i{background:var(--axis)}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin-top:36px;border-top:1px solid var(--grid);border-bottom:1px solid var(--grid)}
.fact{padding:14px 16px 14px 0}.fact b{display:block;font-size:19px;font-weight:650;font-variant-numeric:tabular-nums}.fact span{color:var(--muted);font-size:12.5px}
section{margin-top:52px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:var(--ink2);margin:0 0 6px}
.legend i{display:inline-block;width:14px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}
svg{display:block;overflow:visible;max-width:100%}svg text{fill:var(--muted);font-size:11.5px;font-variant-numeric:tabular-nums}
.chart{position:relative;min-width:0}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--axis);border-radius:var(--r);padding:8px 10px;font-size:12.5px;
box-shadow:0 6px 18px rgba(20,23,26,.14);display:none;white-space:nowrap;z-index:2}.tip b{font-variant-numeric:tabular-nums}
.tablewrap{overflow-x:auto;background:var(--surface);border:1px solid var(--grid);border-radius:var(--r)}
table{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums}
th,td{padding:8px 12px;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}
thead th{color:var(--ink2);font-weight:600;border-bottom:1px solid var(--axis);font-size:12.5px}
tbody tr+tr td{border-top:1px solid var(--grid)}
tbody tr.gap td{border-top:1px solid var(--axis)}
th button{all:unset;cursor:pointer;color:inherit;font:inherit}th button:hover{color:var(--ink)}th button:focus-visible{outline:2px solid var(--s1);outline-offset:3px;border-radius:3px}
th[aria-sort] button{color:var(--ink)}th .arr{display:inline-block;width:10px;color:var(--s1)}
td.dsr svg{display:inline-block;vertical-align:middle;margin-right:8px}
.mark{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:7px;border:1.5px solid var(--muted);vertical-align:baseline}
.pass .mark{background:var(--s1);border-color:var(--s1)}.pass{color:var(--ink);font-weight:600}.fail{color:var(--muted)}
.two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:40px;align-items:start}
.cmp{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px 20px;align-items:baseline;margin:0;max-width:440px}
.cmp dt{color:var(--ink2);font-size:14px}.cmp dd{margin:0;font-size:22px;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap}
.cmp dd s{text-decoration:none;color:var(--muted);font-weight:500}.cmp dd em{font-style:normal;color:var(--muted);font-weight:400;padding:0 8px}
.prose p+p{margin-top:10px}.prose{color:var(--ink2);font-size:14.5px;max-width:34em}.prose strong{color:var(--ink)}
.row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px}
.hb{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:9px 12px;align-items:center;font-size:13.5px}
.hb i{display:block;height:12px;border-radius:0 4px 4px 0;background:var(--s1);min-width:2px}.hb span{color:var(--ink2)}.hb b{font-weight:500;font-variant-numeric:tabular-nums;text-align:right}
.hb small{grid-column:1/-1;color:var(--muted);font-size:12px;margin-top:-6px}
.big{font-size:40px;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
ul.plain{margin:14px 0 0;padding:0;list-style:none;color:var(--ink2);font-size:14px}ul.plain li{padding:7px 0;border-top:1px solid var(--grid)}
.flow{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px 32px;margin:0;padding:0;list-style:none}
.flow li{border-left:2px solid var(--s1);padding-left:14px}.flow b{display:block;font-size:15px}.flow span{color:var(--ink2);font-size:13.5px}
select{font:inherit;padding:4px 8px;border-radius:var(--r);border:1px solid var(--axis);background:var(--surface);color:var(--ink);margin-bottom:10px}
.alert{color:var(--warn);font-weight:600}details{margin-top:10px}summary{cursor:pointer;color:var(--ink2);font-size:13px}details .tablewrap{margin-top:8px}
footer{margin-top:56px;padding-top:16px;border-top:1px solid var(--grid);color:var(--muted);font-size:12.5px}
@media (max-width:820px){main{padding:28px 16px 48px}h1{font-size:26px}.hero,.two,.row{grid-template-columns:minmax(0,1fr);gap:28px}
h1 span{display:inline}.flow{grid-template-columns:minmax(0,1fr)}.frow b{font-size:32px}.big{font-size:32px}section{margin-top:40px}.facts{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style></head><body><main>
<header class="hero"><div><span class="tag" id="tag" hidden></span><h1 id="h1"></h1><p class="lead" id="lead"></p></div><div class="funnel" id="funnel"></div></header>
<div class="facts" id="facts"></div>
<div id="app"></div>
<footer>研究记录，不是投资建议；作者不是持牌金融顾问；历史回测不代表未来收益。观察盘只记账、不下单。</footer>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent),PUBLIC=__PUBLIC__;
const COLORS=['var(--s1)','var(--s2)','var(--s3)'];
const pct=(x,d=1)=>x==null||x!==x?'-':(x>0?'+':'')+(x*100).toFixed(d)+'%';
const num=(x,d=2)=>x==null||x!==x?'-':x.toFixed(d);
const int=x=>x==null?'-':Math.round(x).toLocaleString('en-US');
const ymd=s=>s&&s.length===8?s.slice(0,4)+'-'+s.slice(4,6)+'-'+s.slice(6):s;
const el=(t,a={},h='')=>{const e=document.createElement(t);for(const k in a)e.setAttribute(k,a[k]);e.innerHTML=h;return e};
const app=document.getElementById('app'),charts=[];
function section(title,sub){const c=el('section',{},`<h2>${title}</h2>`+(sub?`<p class="sub">${sub}</p>`:''));app.appendChild(c);return c}
// 图表按容器的真实宽度画，窗口变宽变窄时重画，手机上字不会被缩小
function mount(host,draw){const w=el('div',{class:'chart'});host.appendChild(w);const go=()=>draw(w,Math.max(280,w.clientWidth||960));charts.push(go);go();return w}
let lastW=document.documentElement.clientWidth;
new ResizeObserver(()=>{const w=document.documentElement.clientWidth;if(w===lastW)return;lastW=w;requestAnimationFrame(()=>charts.forEach(f=>f()))}).observe(document.documentElement);
function ticks(lo,hi,n){const span=hi-lo||1,step0=span/n,mag=Math.pow(10,Math.floor(Math.log10(step0)));
 const step=[1,2,2.5,5,10].map(m=>m*mag).find(s=>s>=step0);const out=[];for(let v=Math.ceil(lo/step)*step;v<=hi+1e-9;v+=step)out.push(+v.toFixed(10));return out}
// 折线图：一个 y 轴，十字线和悬浮提示，宽屏时在线的末端直接标注
function lineChart(wrap,W,dates,series,fmt,o={}){
 const narrow=W<600,H=o.h||Math.round(Math.min(360,Math.max(220,W*0.36))),m={l:48,r:narrow?12:150,t:12,b:26};
 const all=series.flatMap(s=>s.values.filter(v=>v!=null));let lo=Math.min(...all),hi=Math.max(...all);if(o.zero){lo=Math.min(lo,0);hi=Math.max(hi,0)}
 const pad=(hi-lo)*0.06||0.01;lo-=pad;if(!o.top0)hi+=pad;const n=dates.length;
 const x=i=>m.l+(W-m.l-m.r)*i/(n-1||1),y=v=>m.t+(H-m.t-m.b)*(1-(v-lo)/(hi-lo));
 let s=`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${o.label||''}">`;
 for(const v of ticks(lo,hi,o.h?3:5))s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/><text x="${m.l-8}" y="${y(v)+4}" text-anchor="end">${fmt(v)}</text>`;
 if(o.zero)s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--axis)"/>`;
 const years=[];dates.forEach((d,i)=>{if(i>0&&d.slice(0,4)!==dates[i-1].slice(0,4))years.push([i,d.slice(0,4)])});
 const every=Math.ceil(years.length*40/(W-m.l-m.r));years.forEach(([i,yr],k)=>{if(k%every===0)s+=`<text x="${x(i)}" y="${H-7}" text-anchor="middle">${yr}</text>`});
 const ends=[];series.forEach((sr,k)=>{let p='',pen=false,li=-1,fi=-1;sr.values.forEach((v,i)=>{if(v==null){pen=false;return}if(fi<0)fi=i;p+=(pen?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1);pen=true;li=i});
  if(o.area&&li>=0)s+=`<path d="${p}L${x(li).toFixed(1)} ${y(0)}L${x(fi).toFixed(1)} ${y(0)}Z" fill="${COLORS[k%3]}" opacity=".1"/>`;
  s+=`<path d="${p}" fill="none" stroke="${COLORS[k%3]}" stroke-width="2" stroke-linejoin="round"/>`;if(li>=0)ends.push({k,name:sr.name,yy:y(sr.values[li]),v:sr.values[li]})});
 if(!narrow){ends.sort((a,b)=>a.yy-b.yy);for(let i=1;i<ends.length;i++)if(ends[i].yy-ends[i-1].yy<17)ends[i].yy=ends[i-1].yy+17;
  for(const e of ends)s+=`<circle cx="${W-m.r}" cy="${y(e.v)}" r="4" fill="${COLORS[e.k%3]}" stroke="var(--page)" stroke-width="2"/><text x="${W-m.r+10}" y="${e.yy+4}" style="fill:var(--ink2)">${e.name.length>10?e.name.slice(0,10)+'…':e.name} ${fmt(e.v)}</text>`}
 s+=`<line class="cx" y1="${m.t}" y2="${H-m.b}" stroke="var(--axis)" stroke-dasharray="3 3" style="display:none"/></svg>`;
 wrap.innerHTML=s+'<div class="tip"></div>';const svg=wrap.querySelector('svg'),cx=wrap.querySelector('.cx'),tip=wrap.querySelector('.tip');
 svg.addEventListener('pointermove',ev=>{const r=svg.getBoundingClientRect(),px=(ev.clientX-r.left)/r.width*W;let i=Math.round((px-m.l)/(W-m.l-m.r)*(n-1));i=Math.max(0,Math.min(n-1,i));
  cx.setAttribute('x1',x(i));cx.setAttribute('x2',x(i));cx.style.display='';
  tip.innerHTML=`<div style="color:var(--ink2)">${dates[i]}</div>`+series.map((sr,k)=>`<div><i style="display:inline-block;width:10px;height:3px;background:${COLORS[k%3]};margin-right:6px;vertical-align:middle"></i>${sr.name} <b>${fmt(sr.values[i])}</b></div>`).join('');
  tip.style.display='block';const left=x(i)/W*r.width;tip.style.left=Math.max(0,left>r.width*0.55?left-tip.offsetWidth-12:left+12)+'px';tip.style.top='8px'});
 svg.addEventListener('pointerleave',()=>{cx.style.display='none';tip.style.display='none'});
}
// 柱状图：从 0 起，正负同一把尺；悬浮显示数值
function barChart(wrap,W,labels,values,fmt,o={}){
 const H=o.h||220,m={l:46,r:6,t:12,b:26},vals=values.map(v=>v==null?0:v);let lo=o.lo!=null?o.lo:Math.min(0,...vals),hi=o.hi!=null?o.hi:Math.max(0,...vals);
 const pad=(hi-lo)*0.08||0.01;if(lo<0)lo-=pad;hi+=pad;const y=v=>m.t+(H-m.t-m.b)*(1-(v-lo)/(hi-lo)),bw=(W-m.l-m.r)/labels.length,every=Math.ceil(34/bw);
 let s=`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${o.label||''}">`;
 for(const v of ticks(lo,hi,4))s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/><text x="${m.l-8}" y="${y(v)+4}" text-anchor="end">${fmt(v)}</text>`;
 labels.forEach((lb,i)=>{const v=vals[i],w=Math.max(4,Math.min(bw*0.62,26)),x0=m.l+bw*i+(bw-w)/2,top=Math.min(y(v),y(0)),h=Math.max(Math.abs(y(v)-y(0)),1);
  s+=`<rect data-i="${i}" x="${x0}" y="${top}" width="${w}" height="${h}" rx="3" fill="${v>=0?'var(--s1)':'var(--s2)'}"/>`;
  if(i%every===0)s+=`<text x="${m.l+bw*i+bw/2}" y="${H-7}" text-anchor="middle">${lb}</text>`});
 s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--axis)"/></svg>`;wrap.innerHTML=s+'<div class="tip"></div>';const tip=wrap.querySelector('.tip');
 wrap.querySelectorAll('rect').forEach(rc=>{rc.addEventListener('pointermove',ev=>{const i=+rc.dataset.i,r=wrap.getBoundingClientRect();tip.innerHTML=`${labels[i]} <b>${fmt(values[i])}</b>`;tip.style.display='block';
  tip.style.left=Math.max(0,Math.min(ev.clientX-r.left+12,r.width-tip.offsetWidth-4))+'px';tip.style.top=Math.max(0,ev.clientY-r.top-38)+'px'});rc.addEventListener('pointerleave',()=>tip.style.display='none')});
}
function table(host,head,rows){const w=el('div',{class:'tablewrap'});w.innerHTML='<table><thead><tr>'+head.map(h=>`<th>${h}</th>`).join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(c=>`<td>${c}</td>`).join('')+'</tr>').join('')+'</tbody></table>';host.appendChild(w)}
function picker(host,names,fn){const s=el('select',{'aria-label':'选择'});names.forEach(n=>s.appendChild(el('option',{},n)));host.appendChild(s);const box=el('div');host.appendChild(box);const go=()=>{box.innerHTML='';fn(s.value,box)};s.addEventListener('change',go);go()}

const M=D.meta,R=D.research,names=Object.keys(D.nav.series);
// ───── 开头：一句话结论 + 三级漏斗 ─────
if(!PUBLIC){const t=document.getElementById('tag');t.hidden=false;t.textContent='私有版：含观察盘与监控'}
document.getElementById('h1').innerHTML=`<span>${R.n_trials} 次预先登记的选股因子试验，</span><span>${R.n_shadow} 个撑过多重检验折扣</span>`;
document.getElementById('lead').textContent=`全 A 股${M.n_codes?' '+int(M.n_codes)+' 只股票':''}（含已退市），${M.start.slice(0,4)} 至 ${M.end.slice(0,4)} 年，月度调仓、只做多。通过门槛先提交再看结果；查出回测缺陷后公开勘误，并按原登记重跑。`;
{const r=R.rounds,f=document.getElementById('funnel'),w=v=>(v/R.n_trials*100).toFixed(1)+'%';
 const rows=[[R.n_trials,'登记并跑完的试验'],[R.n_passed,`过了预先登记的门槛（第一轮 ${r[0].n} 过 ${r[0].passed}，第二轮 ${r[1].n} 过 ${r[1].passed}）`],
  [R.n_shadow,`通缩夏普达到 ${R.dsr_pass}（按 ${R.n_trials} 次试验折扣），最高的一个是 ${num(R.max_dsr)}`]];
 f.innerHTML=rows.map(([v,t])=>`<div class="frow${v?'':' zero'}"><b>${v}</b><div><span>${t}</span><i style="width:${w(v)}"></i></div></div>`).join('')
  +'<p class="note" style="margin-top:0">通缩夏普：把一共试过多少次算进去之后，这个超额不是运气的把握程度。</p>'}
{const C=D.coverage,facts=[[`${M.start.slice(0,7)} 至 ${M.end.slice(0,7)}`,'回测区间，月度调仓']];
 if(M.n_codes)facts.push([int(M.n_codes)+' 只','回测股票数，含已退市']);
 if(C)facts.push([int(C.total_rows/1e4)+' 万行','本地数据层']);
 if(D.tests)facts.push([D.tests+' 个','自动化测试']);
 facts.push([M.asof,'页面生成日期']);
 document.getElementById('facts').innerHTML=facts.map(t=>`<div class="fact"><b>${t[0]}</b><span>${t[1]}</span></div>`).join('')}

// ───── 每一次试验 ─────
{const c=section('每一次试验的结果，包括没通过的',`第一轮看排序能力：RankIC 的 t 值不低于 ${R.t_pass}，并且样本外 RankIC 和样本外纯多头超额都为正。第二轮看换成只做多的持仓后的超额：Newey-West t 值不低于 ${R.t_pass}，并且样本外超额为正。纯多头超额为年化、扣交易成本、相对股票池等权。点表头可以排序。`);
 const cols=[['name','试验'],['round','轮次'],['rank_ic','RankIC'],['t','t 值'],['ex_ann','纯多头超额'],['ex_t','超额 t 值'],['oos_ex_ann','样本外超额'],['dsr','通缩夏普'],['passed','预先登记的门槛']];
 const w=el('div',{class:'tablewrap'});c.appendChild(w);let key=null,dir=1;
 const dsr=t=>{if(t.dsr==null)return '<td>-</td>';const x=4+100*Math.max(0,Math.min(1,t.dsr)),tx=4+100*R.dsr_pass;
  return `<td class="dsr"><svg width="108" height="14" aria-hidden="true"><line x1="4" x2="104" y1="7" y2="7" stroke="var(--grid)" stroke-width="2"/><line x1="${tx}" x2="${tx}" y1="1" y2="13" stroke="var(--ink2)" stroke-width="1.5"/><circle cx="${x}" cy="7" r="4" fill="${t.passed?'var(--s1)':'var(--surface)'}" stroke="${t.passed?'var(--s1)':'var(--muted)'}" stroke-width="1.5"/></svg>${num(t.dsr)}</td>`};
 function draw(){const rows=R.trials.slice();if(key)rows.sort((a,b)=>{const va=a[key],vb=b[key];if(va==null&&vb==null)return 0;if(va==null)return 1;if(vb==null)return -1;return(typeof va==='string'?va.localeCompare(vb,'zh'):va-vb)*dir});
  w.innerHTML='<table><thead><tr>'+cols.map(([k,h])=>`<th${key===k?` aria-sort="${dir>0?'ascending':'descending'}"`:''}><button data-k="${k}">${h}<span class="arr">${key===k?(dir>0?'↑':'↓'):''}</span></button></th>`).join('')+'</tr></thead><tbody>'
   +rows.map((t,i)=>`<tr${!key&&i>0&&rows[i-1].round!==t.round?' class="gap"':''}><td>${t.name}</td><td>第 ${t.round} 轮</td><td>${num(t.rank_ic,3)}</td><td>${num(t.t)}</td><td>${pct(t.ex_ann)}</td><td>${num(t.ex_t)}</td><td>${pct(t.oos_ex_ann)}</td>${dsr(t)}<td class="${t.passed?'pass':'fail'}"><span class="mark"></span>${t.shadow?'影子盘候选':t.passed?'通过':'未通过'}</td></tr>`).join('')+'</tbody></table>'}
 w.addEventListener('click',e=>{const b=e.target.closest('button[data-k]');if(!b)return;const k=b.dataset.k;if(key===k)dir=-dir;else{key=k;dir=k==='name'||k==='round'?1:-1}draw()});draw();
 c.appendChild(el('p',{class:'note'},`通缩夏普一栏的竖线是影子盘候选的标准 ${R.dsr_pass}，圆点是这次试验的值，实心表示过了预先登记的门槛。第一轮没有登记超额 t 值，第二轮不重复计算 RankIC，所以各有两栏是空的。`))}

// ───── 勘误 ─────
{const E=R.erratum,c=section('查出回测缺陷之后',''),g=el('div',{class:'two'});c.appendChild(g);
 g.appendChild(el('div',{class:'prose'},`<p>组合模拟里有一个日期标签错误：<strong>${E.rebalances} 个调仓日里有 ${E.dropped} 个持有期被覆盖</strong>，最后还多记了一个收益为 0 的月份。</p>
<p>修正让结果变好了，这正是最该警惕的方向。所以修正代码和能复现问题的失败测试先提交，再重跑；因子、股票池、成本、门槛、试验名单都没有动，试验次数仍是 ${R.n_trials}。</p>
<p>修正前的结果文件和报告都保留，开头加了勘误提示。排序能力的结论（RankIC）不受影响。</p>`));
 const row=(t,a,b)=>`<dt>${t}</dt><dd><s>${a}</s><em>→</em>${b}</dd>`;
 g.appendChild(el('dl',{class:'cmp'},row('月度超额序列的长度（月）',E.periods_before,E.periods_after)+row('第一轮通过数',E.round1_before,E.round1_after)+row('第二轮通过数',E.round2_before,E.round2_after)+row('最高通缩夏普',num(E.max_dsr_before),num(E.max_dsr_after))))}

// ───── 净值、回撤、分年超额 ─────
{const c=section('净值、回撤和分年超额',M.nav_note||'扣交易成本、含涨跌停约束的回测净值，期初为 1。两个缓冲带组合没有达到影子盘候选的标准，只作为每月记账的观察对象，不是通过检验的策略。');
 c.appendChild(el('div',{class:'legend'},names.map((n,k)=>`<span><i style="background:${COLORS[k%3]}"></i>${n}</span>`).join('')));
 mount(c,(w,W)=>lineChart(w,W,D.nav.dates,names.map(n=>({name:n,values:D.nav.series[n]})),v=>num(v,2),{label:'归一化净值'}));
 if(D.drawdown){c.appendChild(el('h3',{style:'margin-top:18px'},'回撤：净值距离此前最高点的跌幅'));
  mount(c,(w,W)=>lineChart(w,W,D.nav.dates,names.map(n=>({name:n,values:D.drawdown[n]})),v=>(v*100).toFixed(0)+'%',{h:170,zero:true,top0:true,area:true,label:'回撤'}))}
 const ys=Object.keys(D.yearly||{});if(ys.length){c.appendChild(el('h3',{style:'margin-top:22px'},'分年净超额：组合扣成本后的收益减去股票池等权'));
  const all=ys.flatMap(k=>Object.values(D.yearly[k])),lo=Math.min(0,...all),hi=Math.max(0,...all),row=el('div',{class:'row'});c.appendChild(row);
  ys.forEach(k=>{const b=el('div');row.appendChild(b);b.appendChild(el('p',{class:'note',style:'margin:0 0 4px'},k));const yy=Object.keys(D.yearly[k]);
   mount(b,(w,W)=>barChart(w,W,yy.map(y=>W<520?"'"+y.slice(2):y),yy.map(y=>D.yearly[k][y]),v=>pct(v,0),{lo,hi,label:k+' 分年净超额'}))})}
 const d=el('details',{},'<summary>查看净值数据表（每年最后一个点）</summary>');const rows=[];D.nav.dates.forEach((dt,i)=>{if(i===D.nav.dates.length-1||D.nav.dates[i+1].slice(0,4)!==dt.slice(0,4))rows.push([dt,...names.map(n=>num(D.nav.series[n][i],3))])});
 table(d,['日期',...names],rows);c.appendChild(d)}

// ───── 数据层 ─────
if(D.coverage){const C=D.coverage,c=section('数据层','自建的 Tushare 本地缓存：按交易日和报告期分片，原子写入，断点续传，限速和失败重试。下面是缓存里实际数出来的行数。'),g=el('div',{class:'two'});c.appendChild(g);
 const px=C.datasets.filter(d=>d.first>='2010'),first=px.map(d=>d.first).sort()[0],last=C.datasets.map(d=>d.last).sort().pop();
 const li=[`行情类从 ${ymd(first)} 起，最新到 ${ymd(last)}；财务类报告期从 ${ymd(C.datasets.map(d=>d.first).sort()[0])} 起`];
 if(C.stocks)li.push(`股票列表 ${int(C.stocks)} 只，其中已退市 ${int(C.delisted)} 只；日线覆盖 ${int(C.daily_stocks)} 只，其中已退市 ${int(C.delisted_with_daily)} 只`);
 if(C.statement_rows!=null)li.push(`三大报表 ${int(C.statement_rows)} 行，每行带公告日和实际公告日，缺失 ${int(C.ann_date_missing+C.f_ann_date_missing)} 行`);
 g.appendChild(el('div',{},`<div class="big">${int(C.total_rows)}</div><p class="sub" style="margin:4px 0 0">行，${C.datasets.length} 类数据</p><ul class="plain">${li.map(t=>`<li>${t}</li>`).join('')}</ul>`));
 const mx=Math.max(...C.datasets.map(d=>d.rows));
 g.appendChild(el('div',{class:'hb'},C.datasets.map(d=>`<span>${d.label}</span><i style="width:${(d.rows/mx*100).toFixed(1)}%" title="${int(d.rows)} 行"></i><b>${int(d.rows)}</b>`).join('')));
 const miss=C.delisted!=null?`${int(C.delisted-C.delisted_with_daily)} 只已退市股票在缓存区间内没有日线，原因没有逐只核对；`:'';
 c.appendChild(el('p',{class:'note'},`没做的：${miss}只对因子线用到的周线字段和另一个数据源做过逐格对比，财报和 2014 年以前的行情没有交叉核对；财报更正记录是否齐全没有抽查。上面两轮试验用的是另一套行情缓存，还没有基于这批财报数据的因子结果。`))}

// ───── 流程 ─────
if(D.pipeline){const c=section('流程和纪律','每一步都有对应的代码和自动化测试。');c.appendChild(el('ol',{class:'flow'},D.pipeline.map(p=>`<li><b>${p.title}</b><span>${p.detail}</span></li>`).join('')))}

if(!PUBLIC){
// ───── 因子总表 ─────
{const c=section('因子体检总表','RankIC 为全期月度均值；纯多头超额为最高五分之一等权、扣成本、相对股票池等权（年化）。“通过”按第一轮预先登记的门槛。');
 table(c,['名称','RankIC','t','样本外 RankIC','纯多头超额','NW t','样本外超额','月换手','市值中性后超额','第一轮判定'],
  D.table.map(r=>[r.name,num(r.rank_ic,3),num(r.t),num(r.oos_rank_ic,3),pct(r.ex_ann),num(r.ex_t),pct(r.oos_ex_ann),pct(r.turn,0).replace('+',''),pct(r.neutral_ex_ann),r.passed?'通过':'未通过']))}
// ───── RankIC 走势 + 分组收益 ─────
{const c=section('因子 RankIC 走势与五分组收益','左：滚动 12 个月 RankIC 均值；右：五分组年化收益（等权、未扣成本，第 1 组因子值最低）。');
 const have=D.table.map(r=>r.name).filter(n=>D.ic[n]);
 picker(c,have,(n,box)=>{const row=el('div',{class:'row'});box.appendChild(row);const a=el('div'),b=el('div');row.appendChild(a);row.appendChild(b);
  mount(a,(w,W)=>lineChart(w,W,D.ic[n].dates,[{name:'滚动12月',values:D.ic[n].roll}],v=>num(v,3),{zero:true,h:240}));
  const g=D.table.find(r=>r.name===n).groups;mount(b,(w,W)=>barChart(w,W,['第1组','第2组','第3组','第4组','第5组'],g,v=>pct(v,0),{h:240}))})}
// ───── 风格暴露 ─────
{const c=section('风格暴露',`观察盘组合在各因子上的平均标准化值（股票池均值为 0；调仓日 ${M.style_date}）。正值表示组合偏向该因子的高分端。`);
 picker(c,Object.keys(D.style),(n,box)=>{const ks=Object.keys(D.style[n]);mount(box,(w,W)=>barChart(w,Math.min(W,780),ks,ks.map(k=>D.style[n][k]),v=>num(v,2)))})}
// ───── 观察盘与监控 ─────
{const S=D.shadow,c=section('观察盘与监控',`最近调仓日 ${M.rebalance}；数据源 ${S.data?S.data.source:'-'}，最新一周 ${S.data?S.data.last_week:'-'}（距生成日 ${S.stale_days} 天）。`);
 table(c,['组合','目标只数','实际可持有','与上期重合'],Object.entries(S.holdings||{}).map(([k,h])=>[k,h.target_n,h.held_n,h.overlap==null?'首期':pct(h.overlap,0).replace('+','')]));
 c.appendChild(el('h3',{style:'margin-top:18px'},'已实现收益与回测偏差'));
 if((S.realized||[]).length){table(c,['持有期','组合','毛收益','净收益','股票池等权','净超额'],S.realized.map(r=>[r.start+' → '+r.end,r.portfolio,pct(r.gross,2),pct(r.net,2),pct(r.bench,2),pct(r.excess,2)]));
  table(c,['持有期','组合','观察盘','回测口径','偏差'],S.deviation.map(r=>[r.start+' → '+r.end,r.portfolio,pct(r.gross,2),pct(r.backtest_gross,2),pct(r.diff,2)]))}
 else c.appendChild(el('p',{class:'note'},'还没有走完的持有期（只有一期记录），暂无收益和偏差数字。'));
 c.appendChild(el('h3',{style:'margin-top:18px'},'RankIC 衰减监控（最近 12 个月均值不大于 0 记为告警，只提示）'));
 table(c,['因子','全期 RankIC','最近 12 个月','告警'],Object.entries(S.ic_alerts||{}).map(([k,a])=>[k,num(a.full,3),num(a.recent,3),a.alert?'<span class="alert">是</span>':'否']))}
}
</script></body></html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
