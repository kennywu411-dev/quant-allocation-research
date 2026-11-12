"""因子观察盘（只记账、不下单）：python -m quant.alpha.shadow --date 2026-10-30
把指定调仓日的目标持仓写进 live/alpha_shadow/<调仓日>.json。之后每月追加一份，用今后的真实行情算收益
（realized：相邻两期记录之间的实际收益，扣成本，对比股票池等权）。月度流水线见 quant/alpha/pipeline.py。
注意：跟踪的两个组合都没有达到预先登记的“影子盘候选”标准（通缩夏普 ≥ 0.95），这里只是先记账观察，名称是“观察盘”，不是通过检验的策略。"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from quant.alpha import evaluate as E, spec
from quant.factors import evaluate as fev
from quant.alpha.round2 import buffered_sets

OUT = Path("live/alpha_shadow")
TRACKED = ["等权合成+缓冲带", "慢因子合成+缓冲带"]


def targets(b: dict) -> dict:
    """{组合名: {调仓日: 目标集合}}；缓冲带要从头算到最后一个调仓日。"""
    z = {k: E.zscores(v, b["univ"]) for k, v in b["f"].items()}
    ew = E.equal_weighted(z)
    slow = E.equal_weighted({k: z[k] for k in spec.R2_SLOW})
    return {"等权合成+缓冲带": buffered_sets(ew, b["univ"]), "慢因子合成+缓冲带": buffered_sets(slow, b["univ"])}


RETURN_COLS = ["start", "end", "portfolio", "n", "gross", "turn", "cost", "net", "bench", "excess"]


def latest_complete_rebalance(weeks: pd.DatetimeIndex, asof=None) -> pd.Timestamp:
    """最近一个“已经走完”的调仓日：所在周不晚于 asof，且它确实是当月最后一个周五（下一个周五已在下个月）。"""
    from quant.alpha.weekly import rebalance_dates
    asof = pd.Timestamp(asof) if asof is not None else pd.Timestamp.today().normalize()
    rb = rebalance_dates(weeks[weeks <= asof])
    done = [t for t in rb if (t + pd.Timedelta(days=7)).month != t.month]
    if not done:
        raise ValueError("周线缓存里没有完整的调仓月")
    return done[-1]


def actual_holdings(prev: set, want: set, up: set, dn: set, untradable: set) -> tuple[set, float]:
    """目标 → 实际持仓（与回测 evaluate.simulate 同一规则）：涨停的不新买；已持有、跌停或停牌的卖不出。
    返回（实际持仓，单边换手）；首期建仓换手记 1。"""
    new = (want & prev) | ((want - prev) - up) | {c for c in prev - want if c in dn or c in untradable}
    return new, (1.0 if not prev else len(new - prev) / len(new))


def load_records(out: Path = OUT) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(Path(out).glob("20??-??-??.json"))]


def held_of(rec: dict, name: str, prev: set) -> set:
    """某期记录的实际持仓：记录里写了 held 就用它；首期旧格式没有，按规则从目标持仓推出。"""
    if "held" in rec:
        return set(rec["held"][name])
    return actual_holdings(prev, set(rec["portfolios"][name]), set(rec.get("limit_up", [])),
                           set(rec.get("limit_down", [])), set(rec.get("untradable", [])))[0]


def realized(records: list[dict], ret: pd.DataFrame) -> pd.DataFrame:
    """相邻两期记录之间的实际收益。ret = 周收益面板（索引为周五）；持有期 = 调仓周之后到下一个调仓周（含）。
    停牌、退市后收益记 0（与回测一致）；成本 = 单边换手 × 回测同一费率；基准 = 记录里的股票池等权。"""
    records = sorted(records, key=lambda r: r["rebalance"])
    rows, prev = [], {}
    for i, rec in enumerate(records):
        nxt = records[i + 1] if i + 1 < len(records) else None
        if nxt is not None:
            t0, t1 = pd.Timestamp(rec["rebalance"]), pd.Timestamp(nxt["rebalance"])
            win = ret.loc[(ret.index > t0) & (ret.index <= t1)].fillna(0.0)
            cum = (1 + win).prod() - 1
            bench = float(cum.reindex(rec["universe"]).fillna(0.0).mean())
        for name in rec["portfolios"]:
            p = prev.get(name, set())
            held = held_of(rec, name, p)
            turn = 1.0 if not p else len(held - p) / len(held)
            prev[name] = held
            if nxt is None:
                continue
            gross = float(cum.reindex(sorted(held)).fillna(0.0).mean())
            cost = turn * fev.cost_rate(t1)
            rows.append({"start": rec["rebalance"], "end": nxt["rebalance"], "portfolio": name, "n": len(held), "gross": gross,
                         "turn": turn, "cost": cost, "net": gross - cost, "bench": bench, "excess": gross - cost - bench})
    return pd.DataFrame(rows, columns=RETURN_COLS)


def make_record(b: dict, t: pd.Timestamp, prev: dict | None) -> dict:
    """调仓日 t 的观察盘记录：目标持仓、按涨跌停规则得到的实际持仓、股票池。prev = 上一期记录（首期为 None）。"""
    tg = targets(b)
    u = b["univ"].loc[t]
    univ = sorted(u[u].index)
    flag = lambda s: set(s[s].index)
    up, dn, untr = flag(b["up"].loc[t]), flag(b["dn"].loc[t]), flag(~b["tradable"].loc[t])
    held, was = {}, set()
    for k in TRACKED:
        p = held_of(prev, k, set()) if prev else set()
        was |= p
        held[k] = sorted(actual_holdings(p, set(tg[k][t]), up, dn, untr)[0])
    return {"rebalance": str(t.date()), "recorded_at": datetime.now().isoformat(timespec="seconds"),
            "note": "观察盘：未达到预先登记的影子盘候选标准（通缩夏普 < 0.95），先记账观察；只记账不下单。",
            "universe_n": len(univ), "limit_up": sorted(up & set(univ)), "limit_down": sorted(dn & was),
            "untradable": sorted(untr & was), "portfolios": {k: sorted(tg[k][t]) for k in TRACKED}, "held": held,
            "universe": univ}


def write_record(rec: dict, out: Path = OUT) -> Path:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{rec['rebalance']}.json"
    assert not path.exists(), f"{path} 已存在：观察盘记录不允许覆盖"
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    return path


def main(argv: list[str] | None = None) -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from quant.alpha.weekly import build
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="调仓日（周线缓存里的最后一个月末周五）")
    a = ap.parse_args(argv)
    t = pd.Timestamp(a.date)
    b = build(end=a.date)
    assert b["rb"][-1] == t, f"周线缓存的最后一个调仓日是 {b['rb'][-1].date()}，不是 {a.date}"
    recs = [r for r in load_records() if r["rebalance"] < a.date]
    rec = make_record(b, t, recs[-1] if recs else None)
    path = write_record(rec)
    for k in TRACKED:
        print(k, len(rec["portfolios"][k]), "只（实际可持有", len(rec["held"][k]), "只）")
    print("股票池", rec["universe_n"], "只；当周涨停", len(rec["limit_up"]), "只 →", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
