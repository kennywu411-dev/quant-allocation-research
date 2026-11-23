"""第三轮：GRU 序列模型对照（登记见 spec.py 的“第三轮”一节）：python -m quant.alpha.round3
→ research/alpha_round3.json、reports/因子挖掘第三轮-<日期>.md；记一行 trials.csv。"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from quant.alpha import evaluate as E, spec

PRED = Path("research/alpha_round3_gru_pred.parquet")  # GRU 的逐月预测；单独一个进程算出来再读


def channels(w: dict) -> tuple[np.ndarray, np.ndarray]:
    """周线 → (特征 [周, 股票, 通道], 有效标记 [周, 股票])。
    每个通道在当周有成交的股票里取截面分位数再减 0.5；没成交的周填 0。每一周只用当周的截面，不跨时间。"""
    traded = w["traded"].to_numpy(dtype=bool)
    out = []
    for k in spec.R3_CHANNELS:
        x = w[k].where(w["traded"])
        out.append((x.rank(axis=1, pct=True) - 0.5).fillna(0.0).to_numpy(dtype=np.float32))
    return np.stack(out, axis=-1), traded


def windows(X: np.ndarray, valid: np.ndarray, pos: int, cols: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """第 pos 周（含）往前 R3_LOOKBACK 周的序列 [股票, 周, 通道] 和有效周数；历史不够的前面补 0。"""
    L = spec.R3_LOOKBACK
    lo = pos - L + 1
    seg, ok = X[max(lo, 0):pos + 1][:, cols], valid[max(lo, 0):pos + 1][:, cols]
    if lo < 0:
        seg = np.concatenate([np.zeros((-lo, *seg.shape[1:]), dtype=seg.dtype), seg])
    return np.ascontiguousarray(seg.transpose(1, 0, 2)), ok.sum(axis=0)


def _net(seed: int):
    import torch
    torch.manual_seed(seed)

    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = torch.nn.GRU(len(spec.R3_CHANNELS), spec.R3_HIDDEN, batch_first=True)
            self.out = torch.nn.Linear(spec.R3_HIDDEN, 1)

        def forward(self, x):
            return self.out(self.gru(x)[1][-1]).squeeze(-1)

    return Net()


def fit_predict(Xtr: np.ndarray, ytr: np.ndarray, Xte: list[np.ndarray], epochs: int = spec.R3_EPOCHS) -> list[np.ndarray]:
    """每个种子训一个 GRU，返回各测试块预测的种子平均。固定轮数，不早停。"""
    import torch
    torch.set_num_threads(4)
    xt, yt = torch.from_numpy(Xtr), torch.from_numpy(ytr.astype(np.float32))
    preds = [np.zeros(len(x), dtype=np.float64) for x in Xte]
    for seed in spec.R3_SEEDS:
        net = _net(seed)
        opt = torch.optim.Adam(net.parameters(), lr=spec.R3_LR, weight_decay=spec.R3_WEIGHT_DECAY)
        g = torch.Generator().manual_seed(seed)
        for _ in range(epochs):
            net.train()
            perm = torch.randperm(len(xt), generator=g)
            for i in range(0, len(perm), spec.R3_BATCH):
                b = perm[i:i + spec.R3_BATCH]
                opt.zero_grad()
                torch.nn.functional.mse_loss(net(xt[b]), yt[b]).backward()
                opt.step()
        net.eval()
        with torch.no_grad():
            for j, x in enumerate(Xte):
                if len(x):
                    preds[j] += np.concatenate([net(torch.from_numpy(x[i:i + 8192])).numpy()
                                                for i in range(0, len(x), 8192)]) / len(spec.R3_SEEDS)
    return preds


def gru_composite(w: dict, rb: pd.DatetimeIndex, fwd: pd.DataFrame, univ: pd.DataFrame, epochs: int = spec.R3_EPOCHS,
                  log=lambda s: None) -> pd.DataFrame:
    """滚动方式与 E.lgb_composite 相同：每年 12 月末重训，训练集截到上一个调仓日（其标签在 t 已实现）。"""
    X, valid = channels(w)
    weeks, codes = w["close"].index, w["close"].columns
    wpos = dict(zip(rb, weeks.get_indexer(rb)))
    cidx = {c: i for i, c in enumerate(codes)}
    tgt = fwd.where(univ).rank(axis=1, pct=True) - 0.5
    idx = univ.index

    def block(m, need_y: bool):
        ok = univ.loc[m]
        cs = ok[ok].index
        cols = np.array([cidx[c] for c in cs], dtype=int)
        seq, n = windows(X, valid, wpos[m], cols)
        keep = n >= spec.R3_MIN_WEEKS
        y = tgt.loc[m, cs].to_numpy(dtype=float)
        if need_y:
            keep &= ~np.isnan(y)
        return seq[keep], y[keep], cs[keep]

    pred = pd.DataFrame(np.nan, index=idx, columns=univ.columns)
    decembers = [t for t in idx if t.month == 12]
    for k, t in enumerate(decembers):
        pos = idx.get_loc(t)
        train = idx[max(0, pos - spec.LGB_TRAIN_MONTHS):pos]
        if len(train) < 24:
            continue
        tr = [block(m, True) for m in train]
        Xtr, ytr = np.concatenate([b[0] for b in tr]), np.concatenate([b[1] for b in tr])
        end = decembers[k + 1] if k + 1 < len(decembers) else idx[-1] + pd.offsets.MonthEnd(1)
        months = idx[(idx >= t) & (idx < end)]
        te = [block(m, False) for m in months]
        log(f"{t:%Y-%m} 训练 {len(Xtr):,} 条，预测 {len(months)} 个月")
        for m, b, p in zip(months, te, fit_predict(Xtr, ytr, [b[0] for b in te], epochs)):
            pred.loc[m, b[2]] = p
    return pred


def rank_corr(a: pd.DataFrame, b: pd.DataFrame) -> pd.Series:
    """两组预测逐月的截面秩相关。"""
    out = {}
    for t in a.index:
        x = pd.concat([a.loc[t], b.loc[t]], axis=1).dropna()
        if len(x) > 50:
            out[t] = float(x.iloc[:, 0].rank().corr(x.iloc[:, 1].rank()))
    return pd.Series(out)


def render(S: dict, meta: dict) -> str:
    p = lambda x: f"{x * 100:+.1f}%"
    g = S["GRU序列模型"]
    L = [f"# 全 A 股因子挖掘第三轮：GRU 序列模型对照（{meta['date']}）", "",
         "> 研究记录，不是投资建议；历史回测不代表未来收益。作者不是持牌金融顾问。", "",
         "## 问题与做法", "",
         "- 前两轮的输入都是人工定义的因子。本轮让一个小的 GRU 直接读每只股票过去 52 周的周收益、周换手率、周成交额，预测下月收益排序。",
         f"- 登记在 `quant/alpha/spec.py` 第三轮一节（提交 1b25100），写代码和看结果之前提交；累计试验 {meta['n_trials']} 次。",
         f"- 单层 GRU（{spec.R3_HIDDEN} 个隐藏单元），固定训练 {spec.R3_EPOCHS} 轮，不早停、不调参，{len(spec.R3_SEEDS)} 个种子取平均；每年 12 月末用过去 {spec.LGB_TRAIN_MONTHS} 个月重训。",
         "- 股票池、调仓日、成本、涨跌停约束与第一轮周线版相同。2020 年以后的样本外段已被前两轮看过，本轮只作方法对照。", "",
         "## 结果", "",
         f"对照区间：三个模型都有预测的月份（{meta['common_from']} 至 {meta['common_to']}，{meta['n_months']} 个调仓月）。"
         "LightGBM 合成和等权合成两行是在这个区间上重算的对照，它们作为登记试验的判定以第一轮报告为准；本轮新增的试验只有 GRU 一个。", "",
         "| 模型 | 输入 | RankIC | t | 样本外 RankIC | 样本外纯多头超额（年化） | 月均单边换手 | DSR | 按登记门槛 |",
         "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    inputs = {"GRU序列模型": "原始周线序列", "LightGBM合成": "10 个人工因子", "等权合成": "10 个人工因子"}
    for k, s in S.items():
        L.append(f"| {k} | {inputs[k]} | {s['rank_ic']:.3f} | {s['t']:.2f} | {s['oos_rank_ic']:.3f} | {p(s['oos_ex_ann'])} | "
                 f"{s['top_turn']:.0%} | {s['dsr']:.2f} | {'通过' if s['passed'] else '未通过'} |")
    L += ["", "样本外逐月 RankIC 之差（GRU 减对照，Newey-West t，滞后 3）：" + "；".join(
        f"对{k} {v['diff']:+.3f}（t {v['t']:.2f}，{v['n']} 个月）" for k, v in meta["vs"].items()) + "。",
          f"GRU 预测与 LightGBM 预测逐月截面秩相关的均值：{meta['corr_lgb']:.2f}。",
          f"影子盘候选（通过且 DSR ≥ {spec.R2_DSR_PASS}）：{'是' if g['shadow'] else '否'}。", "",
          "## 局限", "",
          "- 只有周线的收益、换手、成交额三个通道，没有财务、行业和盘口信息；模型很小，结论不代表更大的模型或日线、分钟线数据做不出来。",
          "- 样本外段不干净（见上）；真正的检验是之后的行情。",
          "- 周线没有 ST 标记，涨跌停按周涨跌幅近似（与第一轮周线版相同的偏离）。", "",
          "## 复现", "", "```bash", "PYTHONPATH=. .venv/bin/python -m quant.alpha.round3", "```", "",
          f"运行编号 `{meta['run_id']}`。", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    import warnings
    warnings.filterwarnings("ignore")
    from quant.alpha.weekly import build
    from quant.llm_events.study import nw_t
    from quant.research.registry import log_trial, new_run_id
    from quant.research.stats import deflated_sharpe
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--gru-only", action="store_true", help="只训练 GRU 并把预测存到 PRED（由主流程在子进程里调用）")
    a = ap.parse_args(argv)
    b = build()
    f, fwd, univ = b["f"], b["fwd"], b["univ"]
    if a.gru_only:
        gru_composite(b["w"], b["rb"], fwd, univ, log=lambda s: print(s, flush=True)).to_parquet(PRED)
        return 0
    # macOS 上 PyTorch 和 LightGBM 各带一份 OpenMP，同一进程里先后使用会崩溃，所以 GRU 放在子进程里训练
    subprocess.run([sys.executable, "-W", "ignore", "-m", "quant.alpha.round3", "--gru-only"], check=True)
    args = (fwd, univ, b["up"], b["dn"], b["tradable"])
    preds = {"GRU序列模型": pd.read_parquet(PRED).reindex(index=univ.index, columns=univ.columns),
             "LightGBM合成": E.lgb_composite(f, fwd, univ),
             "等权合成": E.equal_weighted({k: E.zscores(v, univ) for k, v in f.items()})}
    # 对照只在三者都有预测的月份上做（GRU 和 LightGBM 都从第一个训练够 24 个月的 12 月开始）
    common = preds["GRU序列模型"].notna().any(axis=1) & preds["LightGBM合成"].notna().any(axis=1)
    months = common[common].index
    res = {k: E.summarize(v.loc[months], fwd.loc[months], univ.loc[months], *(x.loc[months] for x in args[2:]))
           for k, v in preds.items()}
    var_sr = max(float(json.loads(Path("research/alpha_results.json").read_text())["var_sr"]),
                 float(json.loads(Path("research/alpha_round2.json").read_text())["var_sr"]))
    for r in res.values():
        s = r["summary"]
        s["dsr"] = deflated_sharpe(r["excess"], spec.R3_N_TRIALS, var_sr)
        s["shadow"] = bool(s["passed"] and s["dsr"] >= spec.R2_DSR_PASS)
    oos = lambda s: s[s.index > spec.SPLIT]
    vs = {}
    for k in ("LightGBM合成", "等权合成"):
        dd = (oos(res["GRU序列模型"]["ic"]) - oos(res[k]["ic"])).dropna()
        vs[k] = {"diff": float(dd.mean()), "t": nw_t(dd, 3), "n": int(len(dd))}
    run_id, today = new_run_id(), f"{date.today():%Y-%m-%d}"
    S = {k: r["summary"] for k, r in res.items()}
    log_trial({"name": "因子挖掘第三轮｜GRU序列模型｜全A", "phase": "因子挖掘", "run_id": run_id, **S["GRU序列模型"]})
    meta = {"run_id": run_id, "date": today, "n_trials": spec.R3_N_TRIALS, "var_sr": var_sr, "vs": vs,
            "corr_lgb": float(rank_corr(preds["GRU序列模型"].loc[months], preds["LightGBM合成"].loc[months]).mean()),
            "common_from": f"{months[0]:%Y-%m}", "common_to": f"{months[-1]:%Y-%m}", "n_months": int(len(months))}
    Path("research/alpha_round3.json").write_text(json.dumps({**meta, "trials": S}, ensure_ascii=False, indent=1, default=float))
    Path(f"reports/因子挖掘第三轮-{today}.md").write_text(render(S, meta))
    for k, s in S.items():
        print(f"{k:12s} RankIC {s['rank_ic']:+.3f} t {s['t']:+.2f} 样本外 {s['oos_rank_ic']:+.3f} 纯多头样本外 {s['oos_ex_ann']:+.1%} "
              f"换手 {s['top_turn']:.0%} DSR {s['dsr']:.2f} → {'通过' if s['passed'] else '-'}")
    print("GRU − 对照（样本外 RankIC）：", {k: f"{v['diff']:+.3f} (t {v['t']:.2f})" for k, v in vs.items()}, "与 LightGBM 秩相关", f"{meta['corr_lgb']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
