"""因子挖掘周线版（偏离登记见 spec.py 末尾）：python -m quant.alpha.weekly
→ reports/因子挖掘-<日期>.md、同名 png、research/alpha_results.json；每个检验记一行 trials.csv。"""
import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.alpha import data, evaluate as E, spec
from quant.alpha.weekly_data import WDIR

LIM_MAIN, LIM_GROWTH = 0.10, 0.20


def week_end(d: pd.Series) -> pd.Series:
    """周线日期 → 所在周的周五（停牌时 baostock 的周线日期可能不是周五，统一对齐）。"""
    return pd.to_datetime(d).dt.to_period("W-FRI").dt.end_time.dt.normalize()


def load_weekly(codes: list[str], cache: Path = WDIR) -> dict[str, pd.DataFrame]:
    parts = {k: {} for k in ("close", "amount", "turn", "pctChg")}
    for c in codes:
        p = cache / f"{c}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p)
        d["wk"] = week_end(d.date)
        d = d.drop_duplicates("wk", keep="last").set_index("wk")
        for k in parts:
            parts[k][c] = d[k].astype("float64")
    w = {k: pd.DataFrame(v).sort_index() for k, v in parts.items()}
    traded = w["amount"] > 0
    w["ret"] = (w["pctChg"] / 100).where(traded)
    w["traded"] = traded.fillna(False)
    return w


def rebalance_dates(weeks: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """每个月最后一个周五不晚于月末的那一周（整周都在本月之内结束，不用到下个月的数据）。"""
    s = pd.Series(weeks, index=weeks)
    return pd.DatetimeIndex(s.groupby(weeks.to_period("M")).max().to_numpy())


def limit_pct(codes: pd.Index, rb: pd.DatetimeIndex) -> pd.DataFrame:
    lim = pd.DataFrame(LIM_MAIN, index=rb, columns=codes)
    star = [c for c in codes if c.startswith("sh.688")]
    gem = [c for c in codes if c.startswith(("sz.300", "sz.301"))]
    lim[star] = LIM_GROWTH
    lim.loc[rb >= pd.Timestamp("2020-08-24"), gem] = LIM_GROWTH
    return lim


def factors(w: dict, rb: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    ret = w["ret"]
    r0 = ret.fillna(0.0)
    lg = np.log1p(r0)
    cum = lambda n: np.exp(lg.rolling(n).sum()) - 1
    mkt = ret.mean(axis=1)
    var_m = mkt.rolling(12, min_periods=8).var()
    cov = ret.rolling(12, min_periods=8).cov(mkt)
    var_r = ret.rolling(12, min_periods=8).var()
    resid = (var_r - cov.pow(2).div(var_m, axis=0)).clip(lower=0)
    amt = w["amount"].where(w["amount"] > 0)
    illiq = (ret.abs() / amt).rolling(4, min_periods=2).mean()
    mcap = (w["amount"] / (w["turn"].where(w["turn"] > 0) / 100)).ffill(limit=4)
    L = lg.cumsum().reindex(rb)
    out = {
        "LOWVOL": -ret.rolling(52, min_periods=26).std(),
        "LOWTURN": -w["turn"].where(w["traded"]).rolling(4, min_periods=2).mean(),
        "REV21": -cum(4),
        "SIZE": -np.log(mcap),
        "IVOL": -np.sqrt(resid),
        "ILLIQ": np.log(illiq.where(illiq > 0)),
        "REV5": -r0,
        "REV10": -cum(2),
        "MAX": -ret.rolling(4, min_periods=2).max(),
    }
    res = {k: v.reindex(rb) for k, v in out.items()}
    res["MOM12_1"] = np.exp(L.shift(1) - L.shift(12)) - 1  # 第 t-11 到 t-1 个调仓月
    res["_mcap"] = mcap.reindex(rb)
    return res


def forward_returns(w: dict, rb: pd.DatetimeIndex) -> pd.DataFrame:
    """调仓周 t 收盘到下一个调仓周收盘的复利收益；停牌周记 0，退市后记 0（按最后成交价拿回现金，略偏乐观）。"""
    lg = np.log1p(w["ret"].fillna(0.0)).cumsum().reindex(rb)
    alive = w["ret"].notna().cumsum().reindex(rb)
    return (np.exp(lg.shift(-1) - lg) - 1).where(alive > 0)


def universe(mem: pd.DataFrame, basic: pd.DataFrame, w: dict, mcap: pd.DataFrame, rb: pd.DatetimeIndex) -> pd.DataFrame:
    codes = w["close"].columns
    inm = pd.DataFrame(False, index=rb, columns=codes)
    per = pd.to_datetime(mem.month_end).dt.to_period("M")
    for p, g in mem.groupby(per):
        rows = rb[rb.to_period("M") == p]
        if len(rows):
            inm.loc[rows, inm.columns.intersection(g.code)] = True
    ipo = pd.to_datetime(basic.set_index("code").ipoDate.reindex(codes), errors="coerce")
    aged = pd.DataFrame(rb.to_numpy()[:, None] >= (ipo + pd.Timedelta(days=365)).to_numpy()[None, :], index=rb, columns=codes)
    ok = inm & w["traded"].reindex(rb).fillna(False) & aged & mcap.notna()
    small = mcap.where(ok).rank(axis=1, pct=True) <= spec.SMALL_CUT
    return (ok & ~small).fillna(False)


def main(argv: list[str] | None = None) -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from quant.alpha.report import render
    from quant.alpha.run import charts
    from quant.llm_events.study import nw_t
    from quant.research.registry import log_trial, new_run_id
    from quant.research.stats import deflated_sharpe
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports")
    a = ap.parse_args(argv)
    mem = pd.read_csv(data.DIR / "all_members.csv", dtype=str)
    basic = pd.read_csv(data.DIR / "stock_basic.csv", dtype=str)
    w = load_weekly(sorted(set(mem.code)))
    rb = rebalance_dates(w["close"].index)
    rb = rb[(rb >= spec.START) & (rb <= spec.END)]
    fx = factors(w, rb)
    mcap = fx.pop("_mcap")
    f = {k: fx[k] for k in spec.W_FACTORS}
    fwd = forward_returns(w, rb)
    univ = universe(mem, basic, w, mcap, rb)
    wk_ret = w["ret"].reindex(rb)
    lim = limit_pct(w["close"].columns, rb)
    up, dn = (wk_ret >= lim - 0.001).fillna(False), (wk_ret <= -lim + 0.001).fillna(False)
    tradable = w["traded"].reindex(rb).fillna(False)
    args = (fwd, univ, up, dn, tradable)
    res = {k: E.summarize(v, *args) for k, v in f.items()}
    z = {k: E.zscores(v, univ) for k, v in f.items()}
    comps = {"等权合成": E.equal_weighted(z), "IC加权合成": E.ic_weighted(z, {k: r["ic"] for k, r in res.items()}),
             "LightGBM合成": E.lgb_composite(f, fwd, univ)}
    for k, v in comps.items():
        res[k] = E.summarize(v, *args)
    srs = {k: r["excess"].mean() / r["excess"].std() for k, r in res.items() if len(r["excess"]) > 12}
    var_sr = float(np.var(list(srs.values()), ddof=1))
    for k, r in res.items():
        r["summary"]["dsr"] = deflated_sharpe(r["excess"], spec.W_N_TRIALS, var_sr) if k in srs else float("nan")
    oos = lambda s: s[s.index > spec.SPLIT]
    ml = {}
    for lin in ("等权合成", "IC加权合成"):
        dd = (oos(res["LightGBM合成"]["ic"]) - oos(res[lin]["ic"])).dropna()
        ml[lin] = {"diff": float(dd.mean()), "t": nw_t(dd, 3), "n": int(len(dd))}
    run_id, today = new_run_id(), f"{date.today():%Y-%m-%d}"
    S = {k: r["summary"] for k, r in res.items()}
    for k, s in S.items():
        log_trial({"name": f"因子挖掘周线｜{k}｜全A", "phase": "因子挖掘", "run_id": run_id, **s})
    stem = f"因子挖掘-{today}"
    charts(res, Path(a.out) / f"{stem}.png")
    usz = univ.sum(axis=1)
    meta = {"run_id": run_id, "date": today, "n_codes": int(w["close"].shape[1]), "univ_min": int(usz.replace(0, np.nan).min()),
            "univ_max": int(usz.max()), "univ_median": int(usz.median()), "ml_vs_linear": ml, "var_sr": var_sr, "weekly": True}
    Path("research/alpha_results.json").write_text(json.dumps({**meta, "factors": S}, ensure_ascii=False, indent=1, default=float))
    (Path(a.out) / f"{stem}.md").write_text(render(S, meta, f"{stem}.png", weekly=True))
    print(f"试了 {len(S)} 个，通过 {sum(s['passed'] for s in S.values())} 个")
    for k, s in S.items():
        print(f"{k:12s} RankIC {s['rank_ic']:+.3f} t {s['t']:+.2f} 样本外 {s['oos_rank_ic']:+.3f} 纯多头样本外 {s['oos_ex_ann']:+.1%} → {'通过' if s['passed'] else '-'}")
    print("LightGBM − 线性：", {k: f"{v['diff']:+.3f} (t {v['t']:.2f})" for k, v in ml.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
