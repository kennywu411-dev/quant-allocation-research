"""因子体检：python -m quant.alpha.checkup IVOL        （单个；--all 为全部已登记的因子与线性合成）
→ reports/因子体检/<名称>-<日期>.md，汇总数字写进 research/alpha_checkup.json（看板读取）。

体检是对已登记试验的复现和诊断，不是新试验：不写 trials.csv、不改任何判定结果。
名字不在 spec.py 预先登记名单里的因子，拒绝对真实数据出结果（先登记、提交，再看结果）。"""
import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.alpha import evaluate as E, registry, round2, spec
from quant.factors import evaluate as fev

OUT = Path("reports/因子体检")
JSON = Path("research/alpha_checkup.json")
NO_INDUSTRY = "未做：没有行业分类数据"


def _z(b: dict) -> dict:
    """各因子的截面标准化值，按需计算并缓存在 b 里。"""
    if "_z" not in b:
        b["_z"] = {}
    return b["_z"]


def z_of(name: str, b: dict) -> pd.DataFrame:
    z = _z(b)
    if name not in z:
        z[name] = E.zscores(b["f"][name], b["univ"])
    return z[name]


def _args(b: dict):
    return b["fwd"], b["univ"], b["up"], b["dn"], b["tradable"]


def signal(name: str, b: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(排序用的信号, 做市值中性化时用的信号)。单因子的后者是标准化值，合成的后者就是合成值本身（与第二轮一致）。"""
    if name in b["f"]:
        return b["f"][name], z_of(name, b)
    cache = b.setdefault("_sig", {})
    if name not in cache:
        if name == "等权合成":
            cache[name] = E.equal_weighted({k: z_of(k, b) for k in spec.W_FACTORS})
        elif name == "慢因子合成":
            cache[name] = E.equal_weighted({k: z_of(k, b) for k in spec.R2_SLOW})
        elif name == "IC加权合成":
            ics = {k: fev.ic_series(b["f"][k], b["fwd"], b["univ"]) for k in spec.W_FACTORS}
            cache[name] = E.ic_weighted({k: z_of(k, b) for k in spec.W_FACTORS}, ics)
        elif name == "LightGBM合成":
            cache[name] = E.lgb_composite({k: b["f"][k] for k in spec.W_FACTORS}, b["fwd"], b["univ"])
        else:
            raise KeyError(f"没有名为 {name} 的因子或合成")
    return cache[name], cache[name]


def _ic(ic: pd.Series) -> dict:
    full, ins, oos = fev.ic_summary(ic), fev.ic_summary(ic[ic.index <= spec.SPLIT]), fev.ic_summary(ic[ic.index > spec.SPLIT])
    return {"rank_ic": full["mean"], "t": full["t"], "icir_ann": full["icir_ann"], "win": full["win"], "n": full["n"],
            "is_rank_ic": ins["mean"], "oos_rank_ic": oos["mean"], "oos_t": oos["t"]}


def checkup(name: str, b: dict, allow_unregistered: bool = False) -> dict:
    """b = weekly.build() 的返回值。allow_unregistered 只给合成数据的测试用。"""
    if not registry.preregistered(name) and not allow_unregistered:
        raise PermissionError(f"{name} 不在 spec.py 的预先登记名单里：先登记并提交，再对真实数据出结果")
    f, f_neu = signal(name, b)
    fwd, univ = b["fwd"], b["univ"]
    args = _args(b)
    r1 = E.summarize(f, *args)
    long_only = round2.evaluate(round2.top_sets(f, univ), *args)["summary"]
    buffered = round2.evaluate(round2.buffered_sets(f, univ), *args)
    gr = fev.group_returns(fev.groups(f, univ, fwd), fwd)
    g_ann = [fev.ann_return(gr[g]) for g in sorted(gr.columns)]
    if name == "SIZE":
        neutral = "不适用：因子本身就是市值"
    else:
        fn = round2.neutralize(f_neu, z_of("SIZE", b), univ)
        neutral = {**_ic(fev.ic_series(fn, fwd, univ)), "long_only": round2.evaluate(round2.top_sets(fn, univ), *args)["summary"]}
    return {
        "name": name, "preregistered": registry.preregistered(name),
        "months": [str(r1["ic"].index.min().date()), str(r1["ic"].index.max().date())],
        "ic": _ic(r1["ic"]), "round1": r1["summary"],
        "groups": {"ann": g_ann, "monotonic": bool(all(a < c for a, c in zip(g_ann, g_ann[1:])))},
        "cost": {"top_turn": long_only["top_turn"], "cost_drag_ann": long_only["gross_ex_ann"] - long_only["ex_ann"]},
        "long_only": long_only, "buffered": buffered["summary"], "size_neutral": neutral, "industry_neutral": NO_INDUSTRY,
        "series": {"ic": r1["ic"], "excess": r1["excess"], "buffered_excess": buffered["excess"]},
    }


def _p(x, d=1):
    return "—" if x is None or not np.isfinite(x) else f"{x * 100:+.{d}f}%"


def render(r: dict) -> str:
    ic, lo, bf, n = r["ic"], r["long_only"], r["buffered"], r["size_neutral"]
    L = [f"# 因子体检：{r['name']}", "",
         "> 研究记录，不是投资建议；作者不是持牌金融顾问；历史回测不代表未来收益。", "",
         f"- 区间 {r['months'][0]} 至 {r['months'][1]}；股票池、成本、涨跌停约束与预先登记（`quant/alpha/spec.py`）一致。",
         "- 体检是对已登记试验的复现和诊断，**不是新试验**：不记入 `research/trials.csv`，不改变任何判定结果；"
         "表里没有在 spec 中登记为试验的格子（例如单因子的缓冲带、市值中性）只作诊断，不能据此挑选因子。", "",
         "## RankIC", "",
         "| 全期 RankIC | t | 年化 ICIR | 胜率 | 样本内 | 样本外 | 样本外 t | 月数 |", "|---:|---:|---:|---:|---:|---:|---:|---:|",
         f"| {ic['rank_ic']:.3f} | {ic['t']:.2f} | {ic['icir_ann']:.2f} | {ic['win']:.0%} | {ic['is_rank_ic']:.3f} | {ic['oos_rank_ic']:.3f} | {ic['oos_t']:.2f} | {ic['n']} |", "",
         "## 五分组（等权、未扣成本、年化）", "",
         "| 第 1 组（最低） | 第 2 组 | 第 3 组 | 第 4 组 | 第 5 组（最高） | 是否单调 |", "|---:|---:|---:|---:|---:|---|",
         "| " + " | ".join(_p(x) for x in r["groups"]["ann"]) + f" | {'是' if r['groups']['monotonic'] else '否'} |", "",
         "## 换手与成本", "",
         f"- 最高组月均单边换手 {r['cost']['top_turn']:.0%}；成本拖累（毛超额 − 净超额）年化 {_p(r['cost']['cost_drag_ann'])}。",
         "- 成本口径：往返佣金加滑点 0.25% + 印花税（2023-08-28 前 0.1%，之后 0.05%）。", "",
         "## 纯多头超额（扣成本、含涨跌停约束，相对股票池等权）", "",
         "| 持仓构造 | 年化超额 | Newey-West t | 样本内 | 样本外 | 超额最大回撤 | 月均换手 | 平均持仓只数 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for lab, s in (("最高五分之一", lo), ("缓冲带", bf)):
        L.append(f"| {lab} | {_p(s['ex_ann'])} | {s['ex_t']:.2f} | {_p(s['is_ex_ann'])} | {_p(s['oos_ex_ann'])} | {_p(s['ex_mdd'])} | {s['top_turn']:.0%} | {s['n_hold']:.0f} |")
    L += ["", "## 市值中性", ""]
    if isinstance(n, str):
        L.append(f"- {n}。")
    else:
        s = n["long_only"]
        L += [f"- 每月在股票池内对 SIZE 标准化值做一元回归取残差后：RankIC {n['rank_ic']:.3f}（t {n['t']:.2f}），样本外 {n['oos_rank_ic']:.3f}。",
              f"- 残差最高五分之一纯多头：年化超额 {_p(s['ex_ann'])}（t {s['ex_t']:.2f}），样本外 {_p(s['oos_ex_ann'])}。"]
    L += ["", "## 行业中性", "", f"- {r['industry_neutral']}。行业数据接入后再补，不用别的口径代替。", "",
          "## 复现", "", "```bash", f"PYTHONPATH=. .venv/bin/python -m quant.alpha.checkup {r['name']}", "```", ""]
    return "\n".join(L)


def to_json(r: dict) -> dict:
    """去掉时间序列，只留可以直接写进 JSON 的汇总数字。"""
    return {k: v for k, v in r.items() if k != "series"}


def main(argv: list[str] | None = None) -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from quant.alpha.weekly import build
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--all", action="store_true", help="全部已登记的单因子 + 等权合成、IC加权合成、慢因子合成")
    a = ap.parse_args(argv)
    names = [*spec.W_FACTORS, "等权合成", "IC加权合成", "慢因子合成"] if a.all else a.names
    if not names:
        ap.error("给出因子名，或用 --all")
    b = build()
    OUT.mkdir(parents=True, exist_ok=True)
    done = json.loads(JSON.read_text()) if JSON.exists() else {}
    today = f"{date.today():%Y-%m-%d}"
    for nme in names:
        r = checkup(nme, b)
        (OUT / f"{nme}-{today}.md").write_text(render(r))
        done[nme] = {"date": today, **to_json(r)}
        lo = r["long_only"]
        print(f"{nme:10s} RankIC {r['ic']['rank_ic']:+.3f} t {r['ic']['t']:+.2f}｜纯多头超额 {lo['ex_ann']:+.1%} t {lo['ex_t']:+.2f}｜换手 {lo['top_turn']:.0%} → {OUT / f'{nme}-{today}.md'}")
    JSON.write_text(json.dumps(done, ensure_ascii=False, indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
