"""因子线看板（单文件静态网页）：python -m quant.alpha.dashboard
→ reports/看板/因子看板.html（私有版，完整）与 reports/看板/因子看板-公开版.html（只有归一化净值和流程）。
数据来自周线缓存的回测、research/alpha_checkup.json（体检）和 research/alpha_monitor.json（月度流水线）。
公开版由 public_payload 白名单生成：不含持仓、股票代码、因子名与参数、持仓只数、金额。"""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.alpha import evaluate as E, round2, shadow, spec
from quant.factors import evaluate as fev

OUT = Path("reports/看板")
BENCH = "股票池等权"
PIPELINE = [
    {"title": "数据层", "detail": "全 A 股含退市股的行情缓存，避免幸存者偏差；调仓日只用当周收盘前的数据"},
    {"title": "因子库", "detail": "注册表：写一个函数并登记即可使用；未预先登记的因子拒绝对真实数据出结果"},
    {"title": "评测", "detail": "RankIC、分组、换手与成本、纯多头超额、市值中性；多重检验门槛与通缩夏普"},
    {"title": "组合构造", "detail": "涨跌停与停牌约束、交易成本、降换手的持仓规则；判定门槛先提交再看结果"},
    {"title": "观察盘与监控", "detail": "每月记录目标持仓，用之后的真实行情算收益，对比回测偏差并监控因子衰减"},
    {"title": "看板", "detail": "单文件静态网页；公开版只展示归一化净值与流程"},
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
                     "style_date": str(t_last.date()), "rebalance": monitor.get("rebalance"),
                     "nav_note": "扣交易成本、含涨跌停约束的回测净值。两个缓冲带组合在第二轮未通过门槛（超额 t < 3），是观察盘跟踪对象，不是通过检验的策略。"},
            "nav": {"dates": dates, "series": series}, "ic": ic, "table": table, "style": style,
            "shadow": {k: monitor.get(k) for k in ("holdings", "realized", "deviation", "ic_alerts", "stale_days", "data")}}


def public_payload(p: dict) -> dict:
    """白名单：只留归一化净值（组合改用代号）、流程和少量不敏感的元信息。"""
    names, i = {}, 0
    for k in p["nav"]["series"]:
        if k == BENCH:
            names[k] = "股票池等权基准"
        else:
            names[k] = f"观察组合 {'ABCDEFGH'[i]}"
            i += 1
    meta = {k: p["meta"][k] for k in ("asof", "start", "end", "n_trials") if k in p["meta"]}
    return {"meta": meta, "nav": {"dates": p["nav"]["dates"], "series": {names[k]: v for k, v in p["nav"]["series"].items()}},
            "pipeline": PIPELINE}


def render(p: dict, public: bool) -> str:
    data = json.dumps(p, ensure_ascii=False, default=float).replace("</", "<\\/")
    return (TEMPLATE.replace("__TITLE__", "选股因子研究看板（公开版）" if public else "选股因子研究看板（私有版）")
            .replace("__PUBLIC__", "true" if public else "false").replace("__DATA__", data))


def main(argv: list[str] | None = None) -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from quant.alpha.weekly import build
    monitor = json.loads(Path("research/alpha_monitor.json").read_text())
    checkup = json.loads(Path("research/alpha_checkup.json").read_text())
    p = build_payload(build(), monitor, checkup)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "因子看板.html").write_text(render(p, public=False))
    (OUT / "因子看板-公开版.html").write_text(render(public_payload(p), public=True))
    print(f"净值 {p['meta']['start']} 至 {p['meta']['end']}，{len(p['nav']['dates'])} 个点 → {OUT}/因子看板.html、因子看板-公开版.html")
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--warn:#d03b3b}
@media (prefers-color-scheme:dark){:root{--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--warn:#e66767}}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:15px/1.6 -apple-system,"PingFang SC","Helvetica Neue",sans-serif}
main{max-width:1080px;margin:0 auto;padding:28px 16px 56px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:0 0 4px}.sub{color:var(--ink2);margin:0 0 14px;font-size:13.5px}
.card{background:var(--surface);border:1px solid var(--grid);border-radius:10px;padding:18px;margin-top:16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:16px}
.tile{background:var(--surface);border:1px solid var(--grid);border-radius:10px;padding:14px}.tile b{display:block;font-size:24px;font-variant-numeric:tabular-nums}
.tile span{color:var(--ink2);font-size:12.5px}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:13px;color:var(--ink2);margin:6px 0}.legend i{display:inline-block;width:14px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}
svg{width:100%;height:auto;display:block;overflow:visible}svg text{fill:var(--muted);font-size:11.5px;font-variant-numeric:tabular-nums}
.chart{position:relative}.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--axis);border-radius:8px;padding:8px 10px;font-size:12.5px;
box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;white-space:nowrap;z-index:2}.tip b{font-variant-numeric:tabular-nums}
.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600}
select{font:inherit;padding:4px 8px;border-radius:6px;border:1px solid var(--axis);background:var(--surface);color:var(--ink)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media (max-width:760px){.row{grid-template-columns:1fr}}
.flow{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:8px}.step{border:1px solid var(--grid);border-radius:8px;padding:10px 12px}
.step b{display:block}.step span{color:var(--ink2);font-size:12.5px}.step em{font-style:normal;color:var(--muted);font-size:12px}
.note{color:var(--ink2);font-size:12.5px;margin-top:10px}.alert{color:var(--warn);font-weight:600}details{margin-top:8px}summary{cursor:pointer;color:var(--ink2);font-size:13px}
</style></head><body><main>
<h1>__TITLE__</h1>
<p class="sub" id="lead"></p>
<div class="tiles" id="tiles"></div>
<div id="app"></div>
<p class="note">研究记录，不是投资建议；作者不是持牌金融顾问；历史回测不代表未来收益。观察盘只记账、不下单。</p>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent),PUBLIC=__PUBLIC__;
const COLORS=['var(--s1)','var(--s2)','var(--s3)'];
const pct=(x,d=1)=>x==null||isNaN(x)?'—':(x*100>0?'+':'')+(x*100).toFixed(d)+'%';
const num=(x,d=2)=>x==null||isNaN(x)?'—':x.toFixed(d);
const el=(t,a={},h='')=>{const e=document.createElement(t);for(const k in a)e.setAttribute(k,a[k]);e.innerHTML=h;return e};
const app=document.getElementById('app');
function card(title,sub){const c=el('section',{class:'card'},`<h2>${title}</h2><p class="sub">${sub||''}</p>`);app.appendChild(c);return c}
function ticks(lo,hi,n){const span=hi-lo||1,step0=span/n,mag=Math.pow(10,Math.floor(Math.log10(step0)));
 const step=[1,2,2.5,5,10].map(m=>m*mag).find(s=>s>=step0);const out=[];for(let v=Math.ceil(lo/step)*step;v<=hi+1e-9;v+=step)out.push(+v.toFixed(10));return out}
// 折线图：一个 y 轴，十字线 + 悬浮提示，末端直接标注
function lineChart(host,dates,series,fmt,zero){
 const W=1000,H=340,m={l:52,r:120,t:12,b:28},wrap=el('div',{class:'chart'});host.appendChild(wrap);
 const all=series.flatMap(s=>s.values.filter(v=>v!=null));let lo=Math.min(...all),hi=Math.max(...all);if(zero){lo=Math.min(lo,0);hi=Math.max(hi,0)}
 const pad=(hi-lo)*0.06||0.01;lo-=pad;hi+=pad;const n=dates.length;
 const x=i=>m.l+(W-m.l-m.r)*i/(n-1||1),y=v=>m.t+(H-m.t-m.b)*(1-(v-lo)/(hi-lo));
 let s=`<svg viewBox="0 0 ${W} ${H}" role="img">`;
 for(const v of ticks(lo,hi,5))s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/><text x="${m.l-8}" y="${y(v)+4}" text-anchor="end">${fmt(v)}</text>`;
 if(zero)s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--axis)"/>`;
 let lastYear='';dates.forEach((d,i)=>{const yr=d.slice(0,4);if(yr!==lastYear&&(i===0||d.slice(5,7)==='01')){if(i>0||n<30)s+=`<text x="${x(i)}" y="${H-8}" text-anchor="middle">${yr}</text>`;lastYear=yr}});
 const ends=[];series.forEach((sr,k)=>{let p='',pen=false,li=-1;sr.values.forEach((v,i)=>{if(v==null){pen=false;return}p+=(pen?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1);pen=true;li=i});
  s+=`<path d="${p}" fill="none" stroke="${COLORS[k%3]}" stroke-width="2" stroke-linejoin="round"/>`;if(li>=0)ends.push({k,name:sr.name,yy:y(sr.values[li]),v:sr.values[li]})});
 ends.sort((a,b)=>a.yy-b.yy);for(let i=1;i<ends.length;i++)if(ends[i].yy-ends[i-1].yy<19)ends[i].yy=ends[i-1].yy+19;
 for(const e of ends)s+=`<circle cx="${W-m.r}" cy="${y(e.v)}" r="4" fill="${COLORS[e.k%3]}" stroke="var(--surface)" stroke-width="2"/><text x="${W-m.r+10}" y="${e.yy+4}" style="fill:var(--ink2)">${e.name.length>9?e.name.slice(0,9)+'…':e.name} ${fmt(e.v)}</text>`;
 s+=`<line id="cx" y1="${m.t}" y2="${H-m.b}" stroke="var(--axis)" stroke-dasharray="3 3" style="display:none"/></svg>`;
 wrap.innerHTML=s+'<div class="tip"></div>';const svg=wrap.querySelector('svg'),cx=wrap.querySelector('#cx'),tip=wrap.querySelector('.tip');
 svg.addEventListener('mousemove',ev=>{const r=svg.getBoundingClientRect(),px=(ev.clientX-r.left)/r.width*W;let i=Math.round((px-m.l)/(W-m.l-m.r)*(n-1));i=Math.max(0,Math.min(n-1,i));
  cx.setAttribute('x1',x(i));cx.setAttribute('x2',x(i));cx.style.display='';
  tip.innerHTML=`<div style="color:var(--ink2)">${dates[i]}</div>`+series.map((sr,k)=>`<div><i style="display:inline-block;width:10px;height:3px;background:${COLORS[k%3]};margin-right:6px;vertical-align:middle"></i>${sr.name} <b>${fmt(sr.values[i])}</b></div>`).join('');
  tip.style.display='block';const left=x(i)/W*r.width;tip.style.left=(left>r.width*0.6?left-tip.offsetWidth-12:left+12)+'px';tip.style.top='8px'});
 svg.addEventListener('mouseleave',()=>{cx.style.display='none';tip.style.display='none'});
}
// 柱状图：从 0 起，正负同一把尺；hover 显示数值
function barChart(host,labels,values,fmt){
 const W=Math.max(480,labels.length*78),H=260,m={l:50,r:10,t:14,b:44},wrap=el('div',{class:'chart',style:`max-width:${W}px`});host.appendChild(wrap);
 const vals=values.map(v=>v==null?0:v);let lo=Math.min(0,...vals),hi=Math.max(0,...vals);const pad=(hi-lo)*0.1||0.01;if(lo<0)lo-=pad;hi+=pad;
 const y=v=>m.t+(H-m.t-m.b)*(1-(v-lo)/(hi-lo)),bw=(W-m.l-m.r)/labels.length;
 let s=`<svg viewBox="0 0 ${W} ${H}" role="img">`;for(const v of ticks(lo,hi,4))s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)"/><text x="${m.l-8}" y="${y(v)+4}" text-anchor="end">${fmt(v)}</text>`;
 labels.forEach((lb,i)=>{const v=vals[i],x0=m.l+bw*i+bw*0.2,w=Math.min(bw*0.6,44),top=Math.min(y(v),y(0)),h=Math.max(Math.abs(y(v)-y(0)),1);
  s+=`<rect data-i="${i}" x="${x0+(bw*0.6-w)/2}" y="${top}" width="${w}" height="${h}" rx="3" fill="${v>=0?'var(--s1)':'var(--s2)'}"/><text x="${m.l+bw*i+bw/2}" y="${H-m.b+16}" text-anchor="middle">${lb}</text>`});
 s+=`<line x1="${m.l}" x2="${W-m.r}" y1="${y(0)}" y2="${y(0)}" stroke="var(--axis)"/></svg>`;wrap.innerHTML=s+'<div class="tip"></div>';const tip=wrap.querySelector('.tip');
 wrap.querySelectorAll('rect').forEach(rc=>{rc.addEventListener('mousemove',ev=>{const i=+rc.dataset.i,r=wrap.getBoundingClientRect();tip.innerHTML=`${labels[i]} <b>${fmt(values[i])}</b>`;tip.style.display='block';
  tip.style.left=Math.min(ev.clientX-r.left+12,r.width-tip.offsetWidth-4)+'px';tip.style.top=(ev.clientY-r.top-34)+'px'});rc.addEventListener('mouseleave',()=>tip.style.display='none')});
}
function table(host,head,rows){const w=el('div',{class:'tablewrap'});w.innerHTML='<table><thead><tr>'+head.map(h=>`<th>${h}</th>`).join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(c=>`<td>${c}</td>`).join('')+'</tr>').join('')+'</tbody></table>';host.appendChild(w)}
function picker(host,names,fn){const s=el('select');names.forEach(n=>s.appendChild(el('option',{},n)));host.appendChild(s);const box=el('div');host.appendChild(box);const go=()=>{box.innerHTML='';fn(s.value,box)};s.addEventListener('change',go);go()}

// ───── 头部 ─────
const M=D.meta,names=Object.keys(D.nav.series),last=k=>D.nav.series[k][D.nav.series[k].length-1];
document.getElementById('lead').textContent=`A 股选股因子研究：回测区间 ${M.start} 至 ${M.end}，月度调仓，只做多；数据截至 ${M.asof} 生成。`;
const tiles=[[String(M.n_trials),'累计登记的试验次数（判定门槛先提交再看结果）']];
names.forEach(k=>tiles.push([num(last(k),2),`${k}：期末归一化净值（期初 = 1）`]));
document.getElementById('tiles').innerHTML=tiles.map(t=>`<div class="tile"><b>${t[0]}</b><span>${t[1]}</span></div>`).join('');

// ───── 流程（公开版）─────
if(D.pipeline){const c=card('研究流程','从数据到看板的六层；核心逻辑有自动化测试。');const f=el('div',{class:'flow'});
 D.pipeline.forEach((p,i)=>f.appendChild(el('div',{class:'step'},`<em>第 ${i+1} 层</em><b>${p.title}</b><span>${p.detail}</span>`)));c.appendChild(f)}

// ───── 归一化净值 ─────
{const c=card('归一化净值（期初 = 1）',M.nav_note||'扣交易成本、含涨跌停约束的回测净值；观察组合未通过预先登记的显著性门槛，仅作流程展示。');
 c.appendChild(el('div',{class:'legend'},names.map((n,k)=>`<span><i style="background:${COLORS[k%3]}"></i>${n}</span>`).join('')));
 lineChart(c,D.nav.dates,names.map(n=>({name:n,values:D.nav.series[n]})),v=>num(v,2));
 const d=el('details',{},'<summary>查看数据表（每年最后一个点）</summary>');const rows=[];D.nav.dates.forEach((dt,i)=>{if(i===D.nav.dates.length-1||D.nav.dates[i+1].slice(0,4)!==dt.slice(0,4))rows.push([dt,...names.map(n=>num(D.nav.series[n][i],3))])});
 table(d,['日期',...names],rows);c.appendChild(d)}

if(!PUBLIC){
// ───── 因子总表 ─────
{const c=card('因子体检总表','RankIC 为全期月度均值；纯多头超额 = 最高五分之一等权、扣成本、相对股票池等权（年化）。“通过”按第一轮预先登记的门槛。');
 table(c,['名称','RankIC','t','样本外 RankIC','纯多头超额','NW t','样本外超额','月换手','市值中性后超额','第一轮判定'],
  D.table.map(r=>[r.name,num(r.rank_ic,3),num(r.t),num(r.oos_rank_ic,3),pct(r.ex_ann),num(r.ex_t),pct(r.oos_ex_ann),pct(r.turn,0).replace('+',''),pct(r.neutral_ex_ann),r.passed?'通过':'未通过']))}
// ───── RankIC 走势 + 分组收益 ─────
{const c=card('因子 RankIC 走势与五分组收益','左：滚动 12 个月 RankIC 均值；右：五分组年化收益（等权、未扣成本，第 1 组因子值最低）。');
 const have=D.table.map(r=>r.name).filter(n=>D.ic[n]);
 picker(c,have,(n,box)=>{const row=el('div',{class:'row'});box.appendChild(row);const a=el('div'),b=el('div');row.appendChild(a);row.appendChild(b);
  lineChart(a,D.ic[n].dates,[{name:'滚动12月',values:D.ic[n].roll}],v=>num(v,3),true);
  const g=D.table.find(r=>r.name===n).groups;barChart(b,['第1组','第2组','第3组','第4组','第5组'],g,v=>pct(v,0))})}
// ───── 风格暴露 ─────
{const c=card('风格暴露',`观察盘组合在各因子上的平均标准化值（股票池均值为 0；调仓日 ${M.style_date}）。正值表示组合偏向该因子的高分端。`);
 picker(c,Object.keys(D.style),(n,box)=>{const ks=Object.keys(D.style[n]);barChart(box,ks,ks.map(k=>D.style[n][k]),v=>num(v,2))})}
// ───── 观察盘与监控 ─────
{const S=D.shadow,c=card('观察盘与监控',`最近调仓日 ${M.rebalance}；数据源 ${S.data?S.data.source:'—'}，最新一周 ${S.data?S.data.last_week:'—'}（距生成日 ${S.stale_days} 天）。`);
 table(c,['组合','目标只数','实际可持有','与上期重合'],Object.entries(S.holdings||{}).map(([k,h])=>[k,h.target_n,h.held_n,h.overlap==null?'首期':pct(h.overlap,0).replace('+','')]));
 c.appendChild(el('p',{class:'sub',style:'margin-top:14px'},'已实现收益与回测偏差'));
 if((S.realized||[]).length){table(c,['持有期','组合','毛收益','净收益','股票池等权','净超额'],S.realized.map(r=>[r.start+' → '+r.end,r.portfolio,pct(r.gross,2),pct(r.net,2),pct(r.bench,2),pct(r.excess,2)]));
  table(c,['持有期','组合','观察盘','回测口径','偏差'],S.deviation.map(r=>[r.start+' → '+r.end,r.portfolio,pct(r.gross,2),pct(r.backtest_gross,2),pct(r.diff,2)]))}
 else c.appendChild(el('p',{class:'note'},'还没有走完的持有期（只有一期记录），暂无收益和偏差数字。'));
 c.appendChild(el('p',{class:'sub',style:'margin-top:14px'},'RankIC 衰减监控（最近 12 个月均值 ≤ 0 记为告警，只提示）'));
 table(c,['因子','全期 RankIC','最近 12 个月','告警'],Object.entries(S.ic_alerts||{}).map(([k,a])=>[k,num(a.full,3),num(a.recent,3),a.alert?'<span class="alert">⚠ 是</span>':'否']))}
}
</script></body></html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
