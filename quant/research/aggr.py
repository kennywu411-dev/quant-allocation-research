"""激进版候选网格：python -m quant.research.aggr
合并回撤上限默认 -30%（用户 2026-11-04 决定），2026-11-05 用户放宽到 -50%：python -m quant.research.aggr --mdd -0.5 --w-us <美股账户占比>；候选运行前固定，选法与 P3 相同（合格配对里按样本内合并 CAGR 选最高）。"""
import json
from datetime import date
from pathlib import Path

import pandas as pd

from quant.backtest.strategies import rebalance_dates
from quant.metrics import drawdown, max_drawdown
from quant.research import p3
from quant.research.aggr_data import SYNTH_FEE, leveraged
from quant.research.gates import evaluate
from quant.research.registry import log_trial, new_run_id

AGGR_MDD = -0.30
EQ_LEVELS = [0.8, 0.9, 1.0]
SIGNALS = ["static", "sma10_bond"]
SPLIT_NAME = "债金1比1"
MOM_CODE = "6_Portfolios_ME_Prior_12_2_daily:BIG HiPRIOR"
# 股票部分候选：proxy = 上市前补齐；signal = 用哪个 1 倍指数判断均线；synthetic = 纯代理资产（无真实 ETF）
CANDIDATES_US = {
    "SPY": {}, "QQQ": {}, "SMH": {},
    "SSO": {"proxy": ("lev", "SPY"), "signal": "SPY"},
    "QLD": {"proxy": ("lev", "QQQ"), "signal": "QQQ"},
    "MOMBIG": {"synthetic": ("french", MOM_CODE, 0.01)},
}
CANDIDATES_CN = {
    "510300": {"proxy": ("index", "sh000300")},
    "159915": {"proxy": ("index", "sz399006")},
    "512100": {"proxy": ("csindex", "000852")},
}
SLEEVE_NAMES = {"SPY": "标普500", "QQQ": "纳指100", "SMH": "半导体", "SSO": "2倍标普", "QLD": "2倍纳指",
                "MOMBIG": "大盘动量个股组合", "510300": "沪深300", "159915": "创业板", "512100": "中证1000"}
PICK_PATH = Path("research/aggr_pick.json")


def _cands(label: str) -> dict:
    return CANDIDATES_US if label == "美股账户" else CANDIDATES_CN


def trial_name(label: str, sleeve: str, e: float, signal: str) -> str:
    return f"{label}｜{sleeve}｜股{int(round(e * 100))}%｜{signal}"


def trial_names(label: str) -> list[str]:
    return [trial_name(label, s, e, g) for s in _cands(label) for e in EQ_LEVELS for g in SIGNALS]


def covers_2008(start: pd.Timestamp) -> bool:
    """回测区间要包含 2008 年金融危机（第 6 节第 5 条要求单独检查 2008）。"""
    return start <= pd.Timestamp("2007-06-30")


def account_cfg(label: str, sleeve: str, signal_series: dict | None = None) -> dict:
    a = dict(p3.ACCOUNTS[label])
    c = _cands(label)[sleeve]
    a["eq"] = [sleeve]
    proxy = {k: v for k, v in a.get("proxy", {}).items() if k not in p3.ACCOUNTS[label]["eq"]}
    if "proxy" in c:
        proxy[sleeve] = c["proxy"]
    a["proxy"] = proxy
    if "synthetic" in c:
        a["synthetic"] = {sleeve: c["synthetic"]}
        a["fractional"] = True  # 动量个股组合实盘用碎股实现；代理序列单价远高于初始资金，不用碎股会买不进
    if signal_series:
        a["signal_series"] = signal_series
    return a


def sleeve_setup(label: str, sleeve: str, get_price, get_index, fx: dict, getters: dict) -> tuple[dict, pd.DataFrame, list[str]]:
    """回测网格和方案报告共用：账户配置（含 1 倍指数信号）、价格（含代理补齐、截到共同最后一天）。"""
    c = _cands(label)[sleeve]
    sig = {sleeve: get_price(c["signal"], "US", "etf")} if "signal" in c else None
    a = account_cfg(label, sleeve, sig)
    px, notes = p3.build_prices(a, get_price, get_index, fx, getters)
    return a, _truncate(px), notes


def assert_tradable(target: dict, a: dict) -> None:
    """纯代理资产（如 MOMBIG）不是可下单代码，调仓前必须先展开成具体个股。"""
    bad = [s for s, w in target.items() if w > 0 and s in a.get("synthetic", {})]
    if bad:
        raise ValueError(f"{'、'.join(bad)} 是纯代理资产，不能直接下单：需要先展开成具体个股")


def _truncate(px: pd.DataFrame) -> pd.DataFrame:
    """截到所有资产都有数据的最后一天（French 数据比行情晚约一个月）。"""
    return px.loc[:min(px[c].last_valid_index() for c in px)]


def run_grid(label: str, fx: dict, run_id: str, get_price, get_index, getters: dict) -> tuple[pd.DataFrame, dict, list[str]]:
    rows, navs, notes = [], {}, []
    split = p3.SPLITS[SPLIT_NAME]
    for sleeve in _cands(label):
        a, px, n = sleeve_setup(label, sleeve, get_price, get_index, fx, getters)
        notes += n
        common_start = rebalance_dates(px, "end")[12]
        for e in EQ_LEVELS:
            base = p3._base_weights(a, e, split)
            baseline = None
            for signal in SIGNALS:
                name = trial_name(label, sleeve, e, signal)
                by_mode, cost2, local = p3.run_trial(px, base, signal, a, fx, common_start)
                r = evaluate(by_mode, cost2, baseline=None if signal == "static" else baseline)
                dd = drawdown(by_mode["end"])
                r.update(local_mdd=max_drawdown(local.loc[by_mode["end"].index[0]:]),
                         aud_trough=f"{dd.idxmin():%Y-%m}", start=f"{by_mode['end'].index[0]:%Y-%m-%d}")
                if signal == "static":
                    baseline = by_mode["end"]
                row = {"name": name, "account": label, "sleeve": sleeve, "equity": e, "split": SPLIT_NAME,
                       "signal": signal, "weights": ";".join(f"{k}={v:.3f}" for k, v in base.items()), **r}
                log_trial({**row, "phase": "AGGR", "run_id": run_id})
                rows.append(row)
                navs[name] = by_mode
    res = pd.DataFrame(rows)
    res["eligible"] = p3.eligible(res)
    res["covers_2008"] = pd.to_datetime(res.start).map(covers_2008)
    return res, navs, notes


def cut_navs(navs: dict, end: pd.Timestamp) -> dict:
    return {k: {m: s.loc[:end] for m, s in v.items()} for k, v in navs.items()}


def _pct(x) -> str:
    return "—" if pd.isna(x) else f"{x * 100:.1f}%"


def render(res: dict, table: pd.DataFrame, pick, w_us: float, notes: list[str], as_of: date, end: pd.Timestamp,
           mdd: float = AGGR_MDD) -> str:
    cap = f"{mdd * 100:.0f}%"
    out = [f"# 激进版候选回测（{as_of}）", "",
           f"合并回撤上限 **{cap}**（人民币计，两账户按当前市值加权：美股 {w_us * 100:.1f}%）。"
           f"数据截至 {end:%Y-%m-%d}（French 动量数据比行情晚约一个月，所有候选统一截到这一天）。"
           "样本内截至 2019-12-31。回测区间不含 2008 年的配对只列出、不参与选择（第 6 节要求单独检查 2008）。", "",
           "**候选扩充说明**：原计划 A股只有股票 80–100% 三档，第一次运行后发现这三档历史回撤都深于 -54%，"
           "A股约占总资产 47%，任何配对的合并回撤都压不进 -30%（当时的上限）。因此把 P3 已登记的 80 个 A股方案（股票 0–70%，名称以“P3｜”开头）并入候选。"
           "这是看到结果之后的扩充，会增加过拟合风险，样本外结果要打折看。", ""]
    for label, r in res.items():
        out += [f"## {label}", "", "| 方案 | 起点 | 样本内 | 样本外 | 全期 | 账户回撤（人民币） | 门槛 | 含 2008 |", "|---|---|---|---|---|---|---|---|"]
        for x in r.sort_values("is_cagr", ascending=False).itertuples():
            out.append(f"| {x.name.split('｜', 1)[1]} | {x.start} | {_pct(x.is_cagr)} | {_pct(x.oos_cagr)} | {_pct(x.full_cagr)} | "
                       f"{_pct(x.full_mdd)} | {'过' if x.eligible else '不过'} | {'是' if x.covers_2008 else '否'} |")
        out.append("")
    out += ["## 全部合格配对（含 2008，按样本内合并年化排序，前 10，不论是否满足回撤上限）", ""]
    if table.empty:
        out.append("没有合格配对。")
    else:
        out += [f"| 美股 | A股 | 样本内 | 样本外 | 全期 | 合并最差回撤 | 满足 {cap} |", "|---|---|---|---|---|---|---|"]
        for x in table.sort_values("is_cagr", ascending=False).head(10).itertuples():
            out.append(f"| {x.us.split('｜', 1)[1]} | {x.cn.split('｜', 1)[1]} | {_pct(x.is_cagr)} | {_pct(x.oos_cagr)} | "
                       f"{_pct(x.full_cagr)} | {_pct(x.mdd_worst)} | {'是' if x.mdd_worst >= mdd else '否'} |")
    ok = table[table.mdd_worst >= mdd] if len(table) else table
    if len(ok):
        out += ["", f"## 满足 {cap} 的配对（按样本内合并年化排序，前 10；共 {len(ok)} 个）", "",
                "| 美股 | A股 | 样本内 | 样本外 | 全期 | 合并最差回撤 | 距上限 |", "|---|---|---|---|---|---|---|"]
        for x in ok.sort_values("is_cagr", ascending=False).head(10).itertuples():
            out.append(f"| {x.us.split('｜', 1)[1]} | {x.cn.split('｜', 1)[1]} | {_pct(x.is_cagr)} | {_pct(x.oos_cagr)} | "
                       f"{_pct(x.full_cagr)} | {_pct(x.mdd_worst)} | {(x.mdd_worst - mdd) * 100:.1f} 个百分点 |")
    out.append("")
    if pick:
        out.append(f"**选中**：{pick[0].split('｜', 1)[1]} ＋ {pick[1].split('｜', 1)[1]}。")
    else:
        near = table.sort_values("mdd_worst", ascending=False).head(5) if len(table) else table
        out.append(f"**没有配对满足 {cap}**，不放宽约束。最接近的 5 个：" + "；".join(
            f"{x.us.split('｜', 1)[1]} ＋ {x.cn.split('｜', 1)[1]}（{_pct(x.mdd_worst)}）" for x in near.itertuples()))
    out += ["", "## 数据说明", "", *[f"- {n}" for n in dict.fromkeys(notes)], "",
            "- 2 倍 ETF 上市前（2006-06 前）用每日 2 倍合成序列补齐：扣 0.95% 费率、1 倍无风险借贷成本，"
            "并按真实 SSO/QLD 重叠期校准每年再扣 0.7%（校准用了 2006–2026 全段，含样本外）。"
            "由于美股账户的人民币净值要到 2006-05 才有汇率数据，合成段实际只影响回测开头约一个月。", "", p3.DISCLAIMER, ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import warnings
    ap = argparse.ArgumentParser()
    ap.add_argument("--mdd", type=float, default=AGGR_MDD, help="合并回撤上限，如 -0.5")
    ap.add_argument("--w-us", type=float, default=None, help="美股账户占比；持仓文件过期时手动给")
    args = ap.parse_args(argv)
    mdd = args.mdd
    warnings.filterwarnings("ignore")
    from quant.data.update import get_csindex, get_french, get_index, get_price

    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    rf = get_french("F-F_Research_Data_Factors_daily", "RF").pct_change()
    getters = {"csindex": get_csindex, "french": lambda code: get_french(*code.split(":")),
               "lev": lambda code: leveraged(get_price(code, "US", "etf"), 2, SYNTH_FEE, rf)}
    run_id = new_run_id()
    res, navs, notes = {}, {}, []
    for label in ("美股账户", "A股账户"):
        res[label], navs[label], n = run_grid(label, fx, run_id, get_price, get_index, getters)
        notes += n
    # 裁定（2026-11-04）：A股只有 80–100% 股票时合并回撤压不进 -30%（A股约占 47%），
    # A股候选并入 P3 已登记的 80 个方案（股票 0–70%），名称前缀“P3｜”，报告写明这是看到结果后的扩充
    r3, n3, notes3 = p3.run_account("A股账户", p3.ACCOUNTS["A股账户"], fx, get_price, run_id, get_index, phase="AGGR-P3")
    r3 = r3.assign(name="P3｜" + r3.name, sleeve="P3核心ETF",
                   start=[f"{n3[x]['end'].index[0]:%Y-%m-%d}" for x in r3.name])
    r3["covers_2008"] = pd.to_datetime(r3.start).map(covers_2008)
    navs["A股账户"].update({"P3｜" + k: v for k, v in n3.items()})
    res["A股账户"] = pd.concat([res["A股账户"], r3], ignore_index=True)
    notes += notes3
    from quant.data.update import split_notes
    notes += split_notes()
    end = min(s["end"].index[-1] for v in navs.values() for s in v.values())
    navs = {k: cut_navs(v, end) for k, v in navs.items()}
    w_us = args.w_us if args.w_us is not None else p3.current_w_us(fx)
    sel = {k: r.assign(eligible=r.eligible & r.covers_2008) for k, r in res.items()}
    pick, table = p3.select_pair(sel["美股账户"], sel["A股账户"], navs["美股账户"], navs["A股账户"], w_us, mdd_limit=mdd)
    for x in table.itertuples():
        log_trial({"name": f"配对｜{x.us}｜{x.cn}", "phase": "AGGR-合并", "run_id": run_id, "is_cagr": x.is_cagr,
                   "oos_cagr": x.oos_cagr, "full_cagr": x.full_cagr, "mdd_worst": x.mdd_worst, "w_us": w_us})
    PICK_PATH.write_text(json.dumps({"run_id": run_id, "end": f"{end:%Y-%m-%d}", "w_us": w_us, "mdd": mdd,
                                     "pick": list(pick) if pick else None}, ensure_ascii=False, indent=1))
    as_of = date.today()
    path = Path("reports") / f"激进版-候选-{as_of}.md"
    path.write_text(render(res, table, pick, w_us, notes, as_of, end, mdd))
    print("已生成：", path, "\n选中：", pick, "\n合格配对：", len(table), f"满足 {mdd:.0%}：", int((table.mdd_worst >= mdd).sum()) if len(table) else 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
