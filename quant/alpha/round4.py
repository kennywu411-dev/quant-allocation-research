"""第四轮：从信号到组合（登记见 spec.py 的“第四轮”一节）：python -m quant.alpha.round4
行业与市值中性、结构化风险模型 + 约束优化、容量、收益归因。
→ research/alpha_round4.json、reports/因子挖掘第四轮-<日期>.md；两个试验各记一行 trials.csv。"""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.alpha import evaluate as E, round2, spec
from quant.factors import evaluate as fev

IND_FILE = Path("config/industry_csrc_2026-11-23.csv")  # baostock 证监会行业，2026-11-23 取到的当前分类


# ───────── 行业 ─────────
def industry_labels(codes, path: Path = IND_FILE) -> pd.Series:
    """代码 → 行业标签：制造业（C）用两位大类，其余用门类字母，没有分类的是“未知”。"""
    raw = pd.read_csv(path, dtype=str).fillna("").drop_duplicates("code").set_index("code").industry.reindex(list(codes)).fillna("")
    lab = raw.where(raw.str[:1] != "C", raw.str[:3]).where(raw.str[:1] == "C", raw.str[:1])
    return lab.where(raw != "", "未知")


def merge_small(lab: pd.Series, min_n: int = spec.R4_MIN_IND) -> pd.Series:
    """当期样本里不足 min_n 只的行业并入“其他”。"""
    n = lab.value_counts()
    return lab.where(lab.map(n) >= min_n, "其他")


# ───────── 试验 1：行业 + 市值中性 ─────────
def neutralize_ind_size(f: pd.DataFrame, size_z: pd.DataFrame, univ: pd.DataFrame, lab: pd.Series) -> pd.DataFrame:
    """每月在股票池内把 f 对 行业哑变量 + 市值标准化值 回归，返回残差。"""
    out = pd.DataFrame(np.nan, index=f.index, columns=f.columns)
    for t in f.index:
        m = univ.loc[t]
        d = pd.DataFrame({"y": f.loc[t, m[m].index], "s": size_z.loc[t, m[m].index]}).dropna()
        if len(d) < 100:
            continue
        X = pd.get_dummies(merge_small(lab.reindex(d.index)), dtype=float)
        X["_size"] = d.s
        beta, *_ = np.linalg.lstsq(X.to_numpy(), d.y.to_numpy(), rcond=None)
        out.loc[t, d.index] = d.y.to_numpy() - X.to_numpy() @ beta
    return out


# ───────── 试验 2：风险模型 ─────────
def exposures(t, z: dict, univ: pd.DataFrame, lab: pd.Series) -> pd.DataFrame:
    """调仓日 t 股票池内的暴露矩阵：行业哑变量 + 五个风格的标准化值（缺失记 0）。"""
    m = univ.loc[t]
    cs = m[m].index
    X = pd.get_dummies(merge_small(lab.reindex(cs)), dtype=float)
    X.columns = [f"行业:{c}" for c in X.columns]
    for k in spec.R4_STYLES:
        X[f"风格:{k}"] = z[k].loc[t, cs].fillna(0.0).to_numpy()
    return X


def factor_regressions(z: dict, fwd: pd.DataFrame, univ: pd.DataFrame, lab: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """每个调仓日做一次横截面回归（下期收益 ~ 暴露），返回 因子收益[调仓日 × 因子]、残差[调仓日 × 股票]。
    第 t 行用到 t 之后一个月的收益，所以在调仓日 s 只能用 t < s 的行。"""
    fr, res = {}, {}
    for t in univ.index:
        y = fwd.loc[t]
        if not y.notna().any():
            continue
        X = exposures(t, z, univ, lab)
        ok = y.reindex(X.index).notna()
        Xo, yo = X[ok], y.reindex(X.index)[ok]
        beta, *_ = np.linalg.lstsq(Xo.to_numpy(), yo.to_numpy(), rcond=None)
        fr[t] = pd.Series(beta, index=X.columns)
        res[t] = yo - Xo.to_numpy() @ beta
    return pd.DataFrame(fr).T.sort_index(), pd.DataFrame(res).T.sort_index()


def risk_at(t, cols: pd.Index, codes: pd.Index, fr: pd.DataFrame, res: pd.DataFrame) -> tuple[np.ndarray, np.ndarray] | None:
    """调仓日 t 的因子协方差（月度）和特质方差（月度）。只用 t 之前、标签已实现的月份。"""
    from sklearn.covariance import LedoitWolf
    past = fr.index[fr.index < t][-spec.R4_COV_MONTHS:]
    if len(past) < spec.R4_COV_MIN:
        return None
    F = LedoitWolf().fit(fr.loc[past].reindex(columns=cols).fillna(0.0).to_numpy()).covariance_
    r = res.loc[past].reindex(columns=codes)
    own = r.var(axis=0, ddof=1).where(r.notna().sum(axis=0) >= 12)
    med = float(np.nanmedian(own.to_numpy())) if own.notna().any() else float(np.nanvar(res.loc[past].to_numpy()))
    return F, (0.5 * own.fillna(med) + 0.5 * med).to_numpy()


def solve(zv, X, size_col, F, D, b, prev, lo, hi, budget, forced_turn, turn_cap):
    """一次约束优化。返回权重向量或 None（无解）。"""
    import cvxpy as cp
    n = len(zv)
    w = cp.Variable(n)
    act = w - b
    L = np.linalg.cholesky(F + 1e-12 * np.eye(len(F)))
    ind = [i for i, c in enumerate(X.columns) if c.startswith("行业:")]
    Xv = X.to_numpy()
    cons = [w >= lo, w <= hi, cp.sum(w) == budget,
            cp.abs(Xv[:, ind].T @ act) <= spec.R4_IND_BAND,
            cp.abs(Xv[:, size_col] @ act) <= spec.R4_SIZE_BAND,
            cp.sum_squares(L.T @ (Xv.T @ act)) + cp.sum_squares(cp.multiply(np.sqrt(D), act)) <= spec.R4_TE ** 2 / 12]
    if turn_cap is not None:
        cons.append(0.5 * (cp.norm1(w - prev) + forced_turn) <= turn_cap)
    prob = cp.Problem(cp.Maximize(zv @ w), cons)
    try:
        prob.solve(solver=cp.CLARABEL)
    except cp.SolverError:
        return None
    if prob.status not in ("optimal", "optimal_inaccurate") or w.value is None:
        return None
    return np.clip(w.value, 0, None)


def optimized_weights(sig: pd.DataFrame, z: dict, fwd, univ, up, dn, tradable, lab, fr, res, log=lambda s: None) -> tuple[dict, dict]:
    """逐月求解，返回 {调仓日: 权重 Series（含卖不出而留下的股票）} 和求解情况统计。"""
    W, prev = {}, pd.Series(dtype=float)
    stat = {"n": 0, "relaxed": 0, "unlimited": 0, "failed": 0}
    for t in univ.index:
        X = exposures(t, z, univ, lab)
        cs = X.index
        risk = risk_at(t, X.columns, cs, fr, res)
        if risk is None:
            continue
        F, D = risk
        n = len(cs)
        b = np.full(n, 1.0 / n)
        zv = E.zscores(sig.loc[[t]], univ.loc[[t]]).loc[t, cs].clip(-3, 3).fillna(0.0).to_numpy()
        p_in = prev.reindex(cs).fillna(0.0).to_numpy()
        out = prev[~prev.index.isin(cs)]  # 离开股票池的持仓
        stuck = out[[bool(dn.at[t, c]) or not bool(tradable.at[t, c]) for c in out.index]] if len(out) else out
        forced = float(out.sum() - stuck.sum())
        lo, hi = np.zeros(n), np.full(n, spec.R4_W_MAX)
        upm, dnm = up.loc[t, cs].to_numpy(dtype=bool), dn.loc[t, cs].to_numpy(dtype=bool)
        hi = np.where(upm, np.minimum(hi, p_in), hi)       # 涨停：不能加仓
        lo = np.where(dnm, p_in, lo)                        # 跌停：不能减仓
        hi = np.maximum(hi, lo)
        budget = 1.0 - float(stuck.sum())
        size_col = list(X.columns).index("风格:SIZE")
        caps = [None] if not len(prev) else [spec.R4_TURN, spec.R4_TURN_RELAX, None]
        w = None
        for i, cap in enumerate(caps):
            w = solve(zv, X, size_col, F, D, b, p_in, lo, hi, budget, forced, cap)
            if w is not None:
                stat["relaxed"] += int(len(caps) > 1 and i == 1)
                stat["unlimited"] += int(len(caps) > 1 and i == 2)
                break
        stat["n"] += 1
        if w is None:  # 仍然无解：沿用上期持仓
            stat["failed"] += 1
            if not len(prev):
                continue
            W[t] = prev
            continue
        w = pd.Series(w * budget / w.sum(), index=cs)
        cur = pd.concat([w[w > 1e-6], stuck])
        cur = cur / cur.sum()
        W[t] = prev = cur
        log(f"{t:%Y-%m} 持有 {len(cur)} 只")
    return W, stat


# ───────── 组合收益、容量、归因 ─────────
def sets_to_weights(target: dict, up, dn, tradable) -> dict:
    """与 E.simulate 相同的持仓逻辑（涨停不新买、跌停或停牌卖不出），输出等权权重。"""
    held, W = set(), {}
    for t in sorted(target):
        want = target[t]
        buy_ok = {c for c in want - held if not bool(up.at[t, c])}
        stuck = {c for c in held - want if bool(dn.at[t, c]) or not bool(tradable.at[t, c])}
        new = (want & held) | buy_ok | stuck
        if not new:
            continue
        held = new
        W[t] = pd.Series(1.0 / len(new), index=sorted(new))
    return W


def trades(W: dict) -> dict:
    """{调仓日: 权重变化 Series}；第一期相对空仓。"""
    out, prev = {}, pd.Series(dtype=float)
    for t in sorted(W):
        idx = W[t].index.union(prev.index)
        out[t] = W[t].reindex(idx).fillna(0.0) - prev.reindex(idx).fillna(0.0)
        prev = W[t]
    return out


def weight_returns(W: dict, fwd: pd.DataFrame, univ: pd.DataFrame) -> pd.DataFrame:
    """按权重算月度 毛收益、单边换手、固定费率后的净收益、基准（股票池等权）；索引是持有月份。"""
    rows, tr = {}, trades(W)
    for t in sorted(W):
        if not fwd.loc[t].notna().any():
            continue
        w = W[t]
        gross = float((w * fwd.loc[t, w.index].fillna(0.0)).sum())
        turn = 0.5 * float(tr[t].abs().sum()) if t != min(W) else 1.0
        lab = fev.hold_label(t)
        rows[lab] = {"t": t, "gross": gross, "turn": turn, "net": gross - turn * fev.cost_rate(lab),
                     "bench": float(fwd.loc[t, univ.loc[t]].fillna(0.0).mean())}
    return pd.DataFrame(rows).T.sort_index()


def liquidity(w: dict, rb: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    """调仓日的 日波动（过去 12 周周收益标准差 ÷ √5）和 日均成交额（过去 4 周合计 ÷ 20）。只用 t 及以前的数据。"""
    vol = (w["ret"].rolling(12, min_periods=8).std() / np.sqrt(5)).reindex(rb)
    adv = (w["amount"].fillna(0.0).rolling(4, min_periods=1).sum() / 20).reindex(rb)
    return vol, adv.where(adv > 0)


def impact_costs(W: dict, vol: pd.DataFrame, adv: pd.DataFrame, aum: float) -> pd.DataFrame:
    """平方根冲击：单票冲击比例 = Y × 日波动 × sqrt(成交金额 ÷ 日均成交额)。
    返回每个调仓日的 冲击成本（占组合净值的比例）和 成交额占日均成交额的最大值、95 分位。"""
    rows = {}
    for t, d in trades(W).items():
        d = d[d.abs() > 1e-9]
        v = vol.loc[t].reindex(d.index)
        a = adv.loc[t].reindex(d.index)
        v, a = v.fillna(vol.loc[t].median()), a.fillna(adv.loc[t].median())
        part = aum * d.abs() / a
        rows[t] = {"impact": float((d.abs() * spec.R4_IMPACT_Y * v * np.sqrt(part)).sum()),
                   "part_max": float(part.max()), "part_p95": float(part.quantile(0.95))}
    return pd.DataFrame(rows).T


def capacity_table(W: dict, R: pd.DataFrame, vol, adv) -> dict:
    """各资金规模下的年化净超额（固定费率 + 冲击），以及净超额降到 0 的规模（相邻两档线性插值）。"""
    out = {}
    for aum in spec.R4_AUM:
        ic = impact_costs(W, vol, adv, aum)
        ex = (R.net - R.t.map(ic.impact).astype(float) - R.bench).astype(float)
        out[aum] = {"ex_ann": fev.ann_return(ex), "impact_ann": float(R.t.map(ic.impact).astype(float).mean() * 12),
                    "part_p95": float(ic.part_p95.median()), "part_max": float(ic.part_max.median())}
    xs, ys = list(out), [v["ex_ann"] for v in out.values()]
    cap = None
    for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if y0 > 0 >= y1:
            cap = x0 + (x1 - x0) * y0 / (y0 - y1)
            break
    return {"by_aum": {f"{k:.0f}": v for k, v in out.items()}, "zero_at": cap,
            "note": "最小一档就不为正" if ys[0] <= 0 else ("最大一档仍为正" if cap is None else "")}


def attribution(W: dict, z: dict, fwd, univ, lab, fr: pd.DataFrame) -> dict:
    """优化组合的主动收益（毛）拆成 行业合计、五个风格、特质 三部分，返回年化贡献（月均 × 12）。"""
    rows = {}
    for t, w in W.items():
        if t not in fr.index:
            continue
        X = exposures(t, z, univ, lab)
        a = w.reindex(X.index).fillna(0.0).to_numpy() - 1.0 / len(X)
        contrib = pd.Series(X.to_numpy().T @ a, index=X.columns) * fr.loc[t].reindex(X.columns).fillna(0.0)
        active = float((w * fwd.loc[t, w.index].fillna(0.0)).sum()) - float(fwd.loc[t, X.index].fillna(0.0).mean())
        row = {"行业": float(contrib[[c for c in X.columns if c.startswith("行业:")]].sum())}
        row.update({c.split(":")[1]: float(contrib[c]) for c in X.columns if c.startswith("风格:")})
        row["特质"] = active - float(contrib.sum())
        row["主动收益"] = active
        rows[t] = row
    d = pd.DataFrame(rows).T
    return {"annual": {k: float(v) for k, v in (d.mean() * 12).items()}, "months": int(len(d))}


# ───────── 汇总与报告 ─────────
def summarize(R: pd.DataFrame) -> dict:
    from quant.llm_events.study import nw_t
    ex = (R.net - R.bench).astype(float)
    cut = pd.Timestamp(spec.SPLIT) + pd.offsets.MonthEnd(1)
    o, i = ex[ex.index > cut], ex[ex.index <= cut]
    ann = fev.ann_return
    return {"excess": ex, "summary": {
        "n": int(len(ex)), "ex_ann": ann(ex), "ex_t": nw_t(ex, 3), "is_ex_ann": ann(i) if len(i) else float("nan"),
        "oos_ex_ann": ann(o), "oos_ex_t": nw_t(o, 3), "gross_ex_ann": ann((R.gross - R.bench).astype(float)),
        "ex_mdd": E.max_drawdown(ex), "oos_ex_mdd": E.max_drawdown(o), "te_ann": float(ex.std(ddof=1) * np.sqrt(12)),
        "top_turn": float(R.turn.iloc[1:].astype(float).mean()), "from": f"{R.t.iloc[0]:%Y-%m}", "to": f"{R.t.iloc[-1]:%Y-%m}"}}


def render(S: dict, meta: dict) -> str:
    p = lambda x: "—" if x is None or not np.isfinite(x) else f"{x * 100:+.1f}%"
    yi = lambda x: f"{x / 1e8:g} 亿" if x >= 1e8 else f"{x / 1e4:g} 万"
    L = [f"# 全 A 股因子挖掘第四轮：从信号到组合（{meta['date']}）", "",
         "> 研究记录，不是投资建议；历史回测不代表未来收益。作者不是持牌金融顾问。", "",
         "## 问题与做法", "",
         "- 前三轮回答“信号有没有排序能力”。本轮不加新因子、不加新模型，只做信号之后的环节：行业与市值中性、风险模型与约束优化、容量、收益归因。",
         f"- 信号固定为第一轮的 10 因子等权合成。登记在 `quant/alpha/spec.py` 第四轮一节（提交 3fc070e），写代码和看结果之前提交；累计试验 {meta['n_trials']} 次。",
         "- 行业用 baostock 的证监会行业（2026-11-23 取到的当前分类，不是历史时点的分类，存在轻微前视）；制造业用两位大类，其余用门类。",
         "- 2020 年以后的样本外段已被前几轮看过，本轮说明的是流程和方法，不是可交易的结论。", "",
         "## 两个试验", "",
         "| 试验 | 区间 | 年化超额（扣固定费率） | t | 样本外年化超额 | 样本外 t | 实际跟踪误差 | 月均单边换手 | 超额最大回撤 | DSR | 结果 |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for k, s in S.items():
        tag = "影子盘候选" if s.get("shadow") else ("通过" if s.get("passed") else ("对照" if "passed" not in s else "未通过"))
        L.append(f"| {k} | {s['from']} 至 {s['to']} | {p(s['ex_ann'])} | {s['ex_t']:.2f} | {p(s['oos_ex_ann'])} | {s['oos_ex_t']:.2f} | "
                 f"{s['te_ann']:.1%} | {s['top_turn']:.0%} | {p(s['ex_mdd'])} | {s['dsr']:.2f} | {tag} |")
    o = meta["optimizer"]
    L += ["", f"优化求解 {o['n']} 期：换手上限放宽到 {spec.R4_TURN_RELAX:.0%} 的 {o['relaxed']} 期，不限换手的 {o['unlimited']} 期，无解沿用上期的 {o['failed']} 期；平均持有 {meta['n_hold']:.0f} 只。", "",
          "## 容量（描述，不是试验）", "",
          f"平方根冲击成本，系数 {spec.R4_IMPACT_Y:g}；三个组合都在 {meta['cap_from']} 至 {meta['cap_to']} 上比较。表里是扣掉固定费率和冲击成本后的年化超额。", "",
          "| 组合 | " + " | ".join(yi(a) for a in spec.R4_AUM) + " | 净超额降到 0 的规模 |", "|---|" + "---:|" * (len(spec.R4_AUM) + 1)]
    for k, c in meta["capacity"].items():
        z0 = f"约 {c['zero_at'] / 1e8:.1f} 亿" if c["zero_at"] else c["note"]
        L.append(f"| {k} | " + " | ".join(p(c["by_aum"][f"{a:.0f}"]["ex_ann"]) for a in spec.R4_AUM) + f" | {z0} |")
    a = meta["attribution"]["annual"]
    L += ["", "## 优化组合的收益归因（描述，不是试验）", "",
          f"{meta['attribution']['months']} 个月的主动收益（未扣成本）按风险模型拆开，年化贡献（月均 × 12）：", "",
          "| 主动收益 | 行业 | " + " | ".join(spec.R4_STYLES) + " | 特质 |", "|---:|---:|" + "---:|" * (len(spec.R4_STYLES) + 1),
          f"| {p(a['主动收益'])} | {p(a['行业'])} | " + " | ".join(p(a[k]) for k in spec.R4_STYLES) + f" | {p(a['特质'])} |", "",
          "风格的方向与因子定义一致：SIZE 为正表示偏小市值，LOWVOL 为正表示偏低波动，LOWTURN 为正表示偏低换手，REV21 为正表示偏近一个月跌得多的股票。", "",
          "## 局限", "",
          "- 行业分类不是历史时点的；退市较早的股票没有分类，归在“未知”。",
          "- 上一期权重用目标权重，没有按价格漂移；冲击成本的系数是事先取的 1，没有用真实成交校准。",
          "- 风险模型只有行业和五个价量风格，没有基本面风格；特质方差按 36 个月残差估计。",
          "- 周线没有 ST 标记，涨跌停按周涨跌幅近似（与第一轮周线版相同的偏离）。", "",
          "## 复现", "", "```bash", "PYTHONPATH=. .venv/bin/python -W ignore -m quant.alpha.round4   # 需要 cvxpy", "```", "",
          f"运行编号 `{meta['run_id']}`。", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from quant.alpha.weekly import build
    from quant.research.registry import log_trial, new_run_id
    from quant.research.stats import deflated_sharpe
    b = build()
    f, fwd, univ, up, dn, tradable = b["f"], b["fwd"], b["univ"], b["up"], b["dn"], b["tradable"]
    z = {k: E.zscores(v, univ) for k, v in f.items()}
    sig = E.equal_weighted(z)
    lab = industry_labels(univ.columns)
    # 试验 1
    neu = neutralize_ind_size(sig, z["SIZE"], univ, lab)
    t1 = round2.top_sets(neu, univ)
    r1 = round2.evaluate(t1, fwd, univ, up, dn, tradable)
    # 试验 2
    fr, res = factor_regressions(z, fwd, univ, lab)
    W2, stat = optimized_weights(sig, z, fwd, univ, up, dn, tradable, lab, fr, res, log=lambda s: print(s, flush=True))
    R2 = weight_returns(W2, fwd, univ)
    r2 = summarize(R2)
    start = min(W2)
    var_sr = max(float(json.loads(Path(p).read_text())["var_sr"]) for p in
                 ("research/alpha_results.json", "research/alpha_round2.json", "research/alpha_round3.json"))
    s1 = {**{k: v for k, v in r1["summary"].items() if k != "by_year"}, "te_ann": float(r1["excess"].std(ddof=1) * np.sqrt(12)),
          "from": f"{min(t1):%Y-%m}", "to": f"{R2.t.iloc[-1]:%Y-%m}"}
    S = {"等权合成（行业市值中性）": s1, "优化组合": r2["summary"]}
    for k, r in (("等权合成（行业市值中性）", r1), ("优化组合", r2)):
        s = S[k]
        s["dsr"] = deflated_sharpe(r["excess"], spec.R4_N_TRIALS, var_sr)
        s["passed"] = bool(s["ex_t"] >= spec.R2_T_PASS and s["oos_ex_ann"] > 0)
        s["shadow"] = bool(s["passed"] and s["dsr"] >= spec.R2_DSR_PASS)
    assert list(S) == list(spec.R4_TRIALS)
    # 对照：未中性的等权合成最高组，放在优化组合的同一区间上
    W0 = {t: w for t, w in sets_to_weights(round2.top_sets(sig, univ), up, dn, tradable).items() if t >= start}
    W1 = {t: w for t, w in sets_to_weights(t1, up, dn, tradable).items() if t >= start}
    R0, R1 = weight_returns(W0, fwd, univ), weight_returns(W1, fwd, univ)
    ref = summarize(R0)
    ref["summary"]["dsr"] = deflated_sharpe(ref["excess"], spec.R4_N_TRIALS, var_sr)
    S["等权合成最高组（对照，同区间）"] = ref["summary"]
    vol, adv = liquidity(b["w"], b["rb"])
    cap = {"等权合成最高组（对照）": capacity_table(W0, R0, vol, adv), "等权合成（行业市值中性）": capacity_table(W1, R1, vol, adv),
           "优化组合": capacity_table(W2, R2, vol, adv)}
    run_id, today = new_run_id(), f"{date.today():%Y-%m-%d}"
    for k in spec.R4_TRIALS:
        log_trial({"name": f"因子挖掘第四轮｜{k}｜全A", "phase": "因子挖掘", "run_id": run_id,
                   **{kk: v for kk, v in S[k].items() if kk not in ("from", "to", "te_ann")}})
    meta = {"run_id": run_id, "date": today, "n_trials": spec.R4_N_TRIALS, "var_sr": var_sr, "optimizer": stat,
            "n_hold": float(np.mean([len(w) for w in W2.values()])), "cap_from": f"{start:%Y-%m}", "cap_to": f"{R2.t.iloc[-1]:%Y-%m}",
            "capacity": cap, "attribution": attribution(W2, z, fwd, univ, lab, fr),
            "n_industries": int(merge_small(lab.reindex(univ.columns[univ.iloc[-1]])).nunique())}
    Path("research/alpha_round4.json").write_text(json.dumps({**meta, "trials": S}, ensure_ascii=False, indent=1, default=float))
    Path(f"reports/因子挖掘第四轮-{today}.md").write_text(render(S, meta))
    for k, s in S.items():
        print(f"{k:16s} 超额 {s['ex_ann']:+.1%} t {s['ex_t']:+.2f} 样本外 {s['oos_ex_ann']:+.1%} (t {s['oos_ex_t']:+.2f}) TE {s['te_ann']:.1%} "
              f"换手 {s['top_turn']:.0%} DSR {s['dsr']:.2f} → {'影子盘候选' if s.get('shadow') else '通过' if s.get('passed') else '-'}")
    print("求解", stat, "容量", {k: (v["zero_at"], v["note"]) for k, v in cap.items()})
    print("归因", {k: f"{v:+.1%}" for k, v in meta["attribution"]["annual"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
