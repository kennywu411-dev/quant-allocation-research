"""大模型标注公告标题：结构化输出、Batch API（五折）、按公告编号缓存、批次状态落盘（中断后接着取结果）、花费记账与预算上限。
- 只给模型“去掉公司名的标题”，不给日期、代码和任何之后的信息；
- 每个请求 50 条标题，输出 {"items": [{i, type, direction, strength, material}]}；
- 模型与价格（Batch 五折后，美元 / 百万 token）见 PRICE；预算上限 BUDGET，超出前停止提交并提示抽样。
python -m quant.llm_events.label --model claude-haiku-5-5 [--start 2020-01-01 --end 2026-10-31] [--dry-run]"""
import argparse
import json
import re
import time
from pathlib import Path

import pandas as pd

from quant.llm_events import data

DIR = data.DIR
BUDGET = 20.0  # 美元，全部模型合计
PER_REQ = 50
# 官方价格（2026-11-11 查询 platform.claude.com 模型页），Batch API 五折
PRICE = {"claude-haiku-5-5": (0.10, 0.50), "claude-haiku-4-5": (1.00, 5.00), "claude-opus-5-5": (4.00, 20.00)}
CUTOFF = {"claude-haiku-5-5": "2026-06-30", "claude-haiku-4-5": "2025-07-31", "claude-opus-5-5": "2026-06-30"}  # 训练数据截止（月末）

TYPES = ["业绩预告快报", "定期报告", "回购", "股东或高管增持", "股东或高管减持", "股权激励", "重大合同中标",
         "并购重组", "再融资", "诉讼处罚问询", "分红", "人事变动", "担保关联交易", "停复牌", "程序性文件", "其他"]
DIRS = ["利好", "中性", "利空"]
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["i", "type", "direction", "strength", "material"],
                               "properties": {"i": {"type": "integer"}, "type": {"type": "string", "enum": TYPES},
                                              "direction": {"type": "string", "enum": DIRS},
                                              "strength": {"type": "integer", "enum": [0, 1, 2, 3]},
                                              "material": {"type": "boolean"}}}}}}
SYSTEM = f"""你是 A股公告分类器。每条输入是一条上市公司公告的标题，公司名称已替换为“本公司”。
对每条标题输出：
- type：事件类型，取值之一：{"、".join(TYPES)}。会议决议、议事规则、法律意见书、核查意见、提示性公告等没有新信息的，归“程序性文件”。
- direction：仅凭标题字面判断对股价的方向：利好 / 中性 / 利空。看不出方向就选中性。
- strength：0 = 无影响，1 = 弱，2 = 中，3 = 强。
- material：是否是对投资者有实质信息的事件（程序性文件、例行披露为 false）。
规则：只依据标题文字本身判断；不要使用你对任何具体公司、日期或后续股价、业绩的了解；不要猜测公司身份。
按输入编号 i 逐条输出，条数与输入相同。"""


def mask(title: str, names: list[str]) -> str:
    """去掉公司身份：当前简称、全称（……股份有限公司 / 有限公司）一律换成“本公司”。"""
    # 公司全称片段不能跨过“关于 / 之 / 的 / 及 / 与 / 对 / 和”等连接字，免得把前面的律师事务所等一起换掉
    t = re.sub(r"[^关于之的及与对和、，,。：:\s]{2,30}?(股份有限公司|集团有限公司|有限责任公司|有限公司)", "本公司", title)
    for n in sorted(set(names), key=len, reverse=True):
        if n:
            t = t.replace(n, "本公司")
    return re.sub(r"(本公司)+", "本公司", t)


def chunk_requests(df: pd.DataFrame, model: str, per: int = PER_REQ) -> list[dict]:
    """把（已去名的）标题按 per 条一组切成请求；custom_id = 模型 + 组内首末编号的哈希。"""
    reqs = []
    for k in range(0, len(df), per):
        part = df.iloc[k:k + per]
        lines = "\n".join(f"{j}\t{t}" for j, t in enumerate(part.masked))
        cid = f"{model.replace('claude-', '')}-{part.id.iloc[0]}-{len(part)}"
        params = {"model": model, "max_tokens": 4000, "system": SYSTEM,
                  "messages": [{"role": "user", "content": lines}],
                  "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}}}
        if model == "claude-haiku-5-5":  # 分类任务不需要思考；Haiku 5.5 只在 effort ≤ high 时允许关闭
            params["thinking"] = {"type": "disabled"}
            params["output_config"]["effort"] = "low"
        elif model == "claude-opus-5-5":  # Opus 5.5 不能关闭思考，用 low effort 控制花费
            params["output_config"]["effort"] = "low"
            params["max_tokens"] = 16000
        reqs.append({"custom_id": cid, "params": params, "ids": list(part.id)})
    return reqs


def parse_items(text: str, ids: list[str]) -> pd.DataFrame:
    """模型输出 → 每条一行；编号越界或缺失的丢弃（之后补标）。"""
    items = json.loads(text)["items"]
    rows = [{"id": ids[x["i"]], "type": x["type"], "direction": x["direction"], "strength": int(x["strength"]),
             "material": bool(x["material"])} for x in items if 0 <= x["i"] < len(ids)]
    return pd.DataFrame(rows).drop_duplicates("id")


def cost(model: str, inp: int, out: int, batch: bool = True) -> float:
    pi, po = PRICE[model]
    f = 0.5 if batch else 1.0
    return (inp * pi + out * po) / 1e6 * f


class Ledger:
    """花费记账（data/cache/llm_events/spend.json），所有模型合计不超过 BUDGET。"""
    def __init__(self, path: Path = DIR / "spend.json"):
        self.path = path
        self.d = json.loads(path.read_text()) if path.exists() else {"total": 0.0, "by_model": {}, "log": []}

    def add(self, model: str, inp: int, out: int, note: str, batch: bool = True) -> float:
        if self.path.exists():  # 两个模型的进程可能同时在跑：记账前重读，避免互相覆盖
            self.d = json.loads(self.path.read_text())
        c = cost(model, inp, out, batch)
        self.d["total"] += c
        m = self.d["by_model"].setdefault(model, {"usd": 0.0, "input_tokens": 0, "output_tokens": 0})
        m["usd"] += c; m["input_tokens"] += inp; m["output_tokens"] += out
        self.d["log"].append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": model, "usd": c, "note": note})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.d, ensure_ascii=False, indent=1))
        return c

    def remaining(self) -> float:
        return BUDGET - self.d["total"]


def labels_path(model: str) -> Path:
    return DIR / f"labels_{model}.parquet"


def load_labels(model: str) -> pd.DataFrame:
    p = labels_path(model)
    return pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=["id", "type", "direction", "strength", "material"])


def todo(ann: pd.DataFrame, model: str, start: str, end: str) -> pd.DataFrame:
    """区间内还没有标注的公告。"""
    done = set(load_labels(model).id)
    a = ann[(ann.date >= start) & (ann.date <= end)]
    return a[~a.id.isin(done)].drop_duplicates("id")


def names_map(path: Path = DIR / "names.csv") -> dict[str, list[str]]:
    """股票代码 → 简称列表（当前沪深300 名单的简称；标题里出现旧简称时靠“有限公司”规则兜底）。"""
    if not path.exists():
        import akshare as ak
        df = ak.index_stock_cons_csindex(symbol="000300")
        ex = {"上海": "sh.", "深圳": "sz."}
        out = pd.DataFrame({"code": [next(v for k, v in ex.items() if k in e) + str(s).zfill(6)
                                     for s, e in zip(df["成分券代码"], df["交易所"])], "name": df["成分券名称"]})
        path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(path, index=False)
    n = pd.read_csv(path, dtype=str)
    return {c: [x.replace(" ", ""), x] for c, x in zip(n.code, n.name)}


def run(model: str, start: str, end: str, dry_run: bool = False, poll: int = 60) -> None:
    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    ann = data.load_all()
    nm = names_map()
    a = todo(ann, model, start, end).copy()
    a["masked"] = [mask(t, nm.get(c, [])) for t, c in zip(a.title, a.code)]
    reqs = chunk_requests(a, model)
    led = Ledger()
    # 预算：按一个请求的实测 token 外推（输入用 count_tokens；输出按每条 40 token 估计）
    client = anthropic.Anthropic()
    if reqs:
        r0 = reqs[0]["params"]
        n_in = client.messages.count_tokens(model=model, system=r0["system"], messages=r0["messages"]).input_tokens
        est = cost(model, n_in * len(reqs), 40 * len(a))
        print(f"{model}：待标注 {len(a)} 条，{len(reqs)} 个请求，预计 ${est:.2f}；预算剩余 ${led.remaining():.2f}", flush=True)
        if dry_run:
            return
        if est > led.remaining():
            raise SystemExit("预计花费超过剩余预算：按日期分层抽样后再跑（--start/--end 缩小区间），并在报告里写明抽样方式")
    state_p = DIR / f"batches_{model}.json"
    state = json.loads(state_p.read_text()) if state_p.exists() else {}
    pending = {r["custom_id"]: r for r in reqs}
    for k in range(0, len(reqs), 5000):  # 每批最多 5000 个请求（远低于 10 万上限，单批失败影响小）
        part = [r for r in reqs[k:k + 5000] if not any(r["custom_id"] in b["ids"] for b in state.values())]
        if not part:
            continue
        b = client.messages.batches.create(requests=[Request(custom_id=r["custom_id"],
                                                             params=MessageCreateParamsNonStreaming(**r["params"]))
                                                     for r in part])
        state[b.id] = {"ids": [r["custom_id"] for r in part], "collected": False}
        state_p.write_text(json.dumps(state, indent=1))
        print("已提交批次", b.id, len(part), flush=True)
    labels = load_labels(model)
    for bid, s in state.items():
        if s["collected"]:
            continue
        while (b := client.messages.batches.retrieve(bid)).processing_status != "ended":
            print(bid, b.processing_status, b.request_counts.processing, flush=True)
            time.sleep(poll)
        rows, inp, out, bad = [], 0, 0, 0
        for res in client.messages.batches.results(bid):
            r = pending.get(res.custom_id)
            if res.result.type != "succeeded" or r is None:
                bad += 1
                continue
            msg = res.result.message
            inp += msg.usage.input_tokens + (msg.usage.cache_read_input_tokens or 0) + (msg.usage.cache_creation_input_tokens or 0)
            out += msg.usage.output_tokens
            text = next((x.text for x in msg.content if x.type == "text"), "")
            try:
                rows.append(parse_items(text, r["ids"]))
            except (json.JSONDecodeError, KeyError):
                bad += 1
        led.add(model, inp, out, f"batch {bid}")
        if rows:
            labels = pd.concat([labels, *rows], ignore_index=True).drop_duplicates("id", keep="last")
            labels.to_parquet(labels_path(model), index=False)
        s["collected"] = True
        state_p.write_text(json.dumps(state, indent=1))
        print(f"{bid} 收回：标注 {sum(len(x) for x in rows)} 条，失败请求 {bad} 个，花费累计 ${led.d['total']:.2f}", flush=True)


REVIEW_SEED, REVIEW_START, REVIEW_END = 20261111, "2025-08-01", "2026-10-31"


def review_sample(n: int = 200, seed: int = REVIEW_SEED) -> pd.DataFrame:
    """复核样本：两个 Haiku 都标注过的干净段公告里简单随机抽 n 条（种子固定，运行前写死）。"""
    ann = data.load_all()
    ids = set(load_labels("claude-haiku-5-5").id) & set(load_labels("claude-haiku-4-5").id)
    a = ann[ann.id.isin(ids) & (ann.date >= REVIEW_START) & (ann.date <= REVIEW_END)].sort_values("id")
    return a.sample(n, random_state=seed)


def review(n: int = 200) -> None:
    """用更强的模型（Opus 5.5，同步调用）复核 n 条；结果存 labels_claude-opus-5-5.parquet。"""
    import anthropic
    m = "claude-opus-5-5"
    s = review_sample(n).copy()
    s = s[~s.id.isin(set(load_labels(m).id))]
    nm = names_map()
    s["masked"] = [mask(t, nm.get(c, [])) for t, c in zip(s.title, s.code)]
    client, led, labels = anthropic.Anthropic(), Ledger(), load_labels(m)
    for r in chunk_requests(s, m):
        msg = client.messages.create(**r["params"])
        led.add(m, msg.usage.input_tokens, msg.usage.output_tokens, "复核（同步）", batch=False)
        text = next((b.text for b in msg.content if b.type == "text"), "")
        labels = pd.concat([labels, parse_items(text, r["ids"])], ignore_index=True).drop_duplicates("id", keep="last")
        labels.to_parquet(labels_path(m), index=False)
    print(f"复核完成 {len(labels)} 条；花费累计 ${led.d['total']:.2f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-5-5", choices=list(PRICE))
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-10-31")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--review", type=int, default=0, help="用 Opus 5.5 复核 N 条（忽略 --model 以外的参数）")
    a = ap.parse_args(argv)
    if a.review:
        review(a.review)
    else:
        run(a.model, a.start, a.end, a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
