"""moomoo 模拟盘适配：只允许 SIMULATE 环境。SDK 的交易函数默认 trd_env='REAL'，所以每次调用都显式传入 SIMULATE。
OpenD 由用户自己打开并登录；这里不读、不存任何密码或交易解锁码。"""
import argparse
import os
from pathlib import Path

import pandas as pd

SIMULATE = "SIMULATE"
ACC_ID_FILE = Path("config/moomoo_paper_acc_id.txt")


def paper_acc_id(env: dict = os.environ, path: Path = ACC_ID_FILE) -> int:
    """固定使用的模拟账户号：环境变量 MOOMOO_PAPER_ACC_ID 优先，其次 config/moomoo_paper_acc_id.txt（不公开）。
    报名比赛后可能多出模拟账户，不能靠排序选；用 --check 查到后填进去。没配置时返回 0。"""
    v = env.get("MOOMOO_PAPER_ACC_ID") or (path.read_text().strip() if path.exists() else "")
    return int(v) if v else 0


PAPER_ACC_ID = paper_acc_id()
BAND = 0.005  # 限价 = 参考价 ±0.5%
SIDE = {"买": "BUY", "卖": "SELL"}
PAPER_DIR = Path("live/paper")


def to_code(symbol: str) -> str:
    return symbol if symbol.startswith("US.") else f"US.{symbol}"


class PaperBroker:
    def __init__(self, client=None, host: str = "127.0.0.1", port: int = 11111, env: str = SIMULATE):
        if env != SIMULATE:
            raise ValueError("只允许模拟盘（SIMULATE），不能连接真实账户")
        self.env = SIMULATE
        self.acc_id = PAPER_ACC_ID
        if not self.acc_id:
            raise ValueError("没有配置模拟账户号：设置 MOOMOO_PAPER_ACC_ID，或写进 config/moomoo_paper_acc_id.txt（--check 可查）")
        if client is None:
            try:
                from moomoo import OpenSecTradeContext, SecurityFirm, TrdMarket
            except ImportError as e:
                raise RuntimeError("没有安装 moomoo-api：.venv/bin/pip install moomoo-api") from e
            client = OpenSecTradeContext(filter_trdmarket=TrdMarket.US, host=host, port=port,
                                         security_firm=SecurityFirm.FUTUAU)
        self._client = client

    def _call(self, name: str, *args, **kw) -> pd.DataFrame:
        ret, data = getattr(self._client, name)(*args, trd_env=self.env, acc_id=self.acc_id, **kw)
        if ret != 0:
            raise RuntimeError(f"moomoo {name} 失败：{data}（请确认 OpenD 已打开并登录）")
        return data

    def positions(self) -> pd.DataFrame:
        return self._call("position_list_query")

    def cash(self) -> float:
        return float(self._call("accinfo_query", currency="USD").cash.iloc[0])

    def place_limit(self, symbol: str, side: str, qty: int, price: float) -> str:
        d = self._call("place_order", round(price, 2), qty, to_code(symbol), SIDE[side], order_type="NORMAL")
        return str(d.order_id.iloc[0])

    def cancel(self, order_id: str) -> None:
        self._call("modify_order", "CANCEL", order_id, 0, 0)

    def orders(self) -> pd.DataFrame:
        """当天订单。"""
        return self._fmt(self._call("order_list_query"))

    def history_orders(self, start: str, end: str) -> pd.DataFrame:
        """跨日订单（偏差报告用），日期格式 YYYY-MM-DD。"""
        return self._fmt(self._call("history_order_list_query", start=f"{start} 00:00:00", end=f"{end} 23:59:59"))

    @staticmethod
    def _fmt(d: pd.DataFrame) -> pd.DataFrame:
        return d.rename(columns={"order_status": "status"})[
            ["order_id", "code", "trd_side", "qty", "price", "status", "dealt_qty", "dealt_avg_price"]]

    def close(self) -> None:
        if hasattr(self._client, "close"):
            self._client.close()


def mirror_orders(shadow_positions: dict, paper: pd.DataFrame, prices: dict) -> pd.DataFrame:
    """让模拟盘持仓跟上影子盘：按差额下单，卖出不超过模拟盘已有持仓（融资模拟账户卖出未持有的股票会变成做空）。"""
    held = {c.removeprefix("US."): int(q) for c, q in zip(paper.code, paper.qty) if q > 0}
    rows = []
    for s in sorted(set(held) | set(shadow_positions)):
        d = int(shadow_positions.get(s, 0)) - held.get(s, 0)
        if d != 0:
            rows.append({"symbol": s, "side": "买" if d > 0 else "卖", "shares": abs(d), "price": prices[s],
                         "value": abs(d) * prices[s], "cost": 0.0})
    o = pd.DataFrame(rows, columns=["symbol", "side", "shares", "price", "value", "cost"])
    return o.sort_values("side", key=lambda x: x.map({"卖": 0, "买": 1}), kind="stable").reset_index(drop=True)


def sync_orders(broker: PaperBroker, orders: pd.DataFrame, log_path: Path, force: bool = False) -> pd.DataFrame:
    """按月度调仓单在模拟盘下限价单（先卖后买；买 +0.5%、卖 -0.5%），记录订单号和参考价。同月已下过单时拒绝，避免重复下单。"""
    if log_path.exists() and not force:
        raise FileExistsError(f"{log_path} 已存在：本月已下过模拟单。确需再下请加 --force（会另存记录）")
    if log_path.exists():
        log_path = log_path.with_name(f"{log_path.stem}-{pd.Timestamp.now():%H%M%S}.csv")
    rows = []
    trades = orders[orders.symbol != "CASH"].sort_values("side", key=lambda s: s.map({"卖": 0, "买": 1}))
    for r in trades.itertuples():
        limit = r.price * (1 + BAND if r.side == "买" else 1 - BAND)
        oid = broker.place_limit(r.symbol, r.side, int(r.shares), limit)
        rows.append({"order_id": oid, "symbol": r.symbol, "side": r.side, "shares": int(r.shares),
                     "ref_price": r.price, "limit": round(limit, 2)})
    log = pd.DataFrame(rows, columns=["order_id", "symbol", "side", "shares", "ref_price", "limit"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log.to_csv(log_path, index=False)
    return log


def check(host: str, port: int) -> int:
    """连通测试：查资金、持仓，下 1 股 SPY 远低于市价的限价买单再撤掉。"""
    from quant.data.update import latest_price
    b = PaperBroker(host=host, port=port)
    try:
        ret, accs = b._client.get_acc_list()
        if ret == 0:
            print("模拟账户：", accs[accs.trd_env == SIMULATE][["acc_id", "trdmarket_auth"]].to_string(index=False))
        print("模拟账户现金（USD）：", b.cash())
        print("模拟账户持仓：\n", b.positions())
        px = round(latest_price("SPY", "US", "etf") * 0.5, 2)
        oid = b.place_limit("SPY", "买", 1, px)
        print(f"已下测试单 {oid}（1 股 SPY @ {px}，远低于市价不会成交）")
        b.cancel(oid)
        import time
        for _ in range(10):  # 撤单是异步的，等状态更新
            o = b.orders()
            st = o[o.order_id.astype(str) == str(oid)].status
            if not st.empty and st.iloc[0].startswith("CANCELLED"):
                break
            time.sleep(1)
        print("撤单后状态：", st.iloc[0] if not st.empty else "未查到")
    finally:
        b.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="moomoo 模拟盘（只允许 SIMULATE）")
    ap.add_argument("--check", action="store_true", help="连通测试：查询、下单、撤单")
    ap.add_argument("--sync", metavar="YYYY-MM", help="让模拟盘持仓跟上影子盘（按差额下限价单）")
    ap.add_argument("--force", action="store_true", help="同月再下一次（记录另存）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=11111)
    a = ap.parse_args()
    if a.check:
        return check(a.host, a.port)
    if a.sync:
        import json
        from quant.data.update import latest_price
        st = json.loads(Path("live/shadow/美股账户.json").read_text())
        b = PaperBroker(host=a.host, port=a.port)
        try:
            pos = b.positions()
            syms = set(st["positions"]) | {c.removeprefix("US.") for c in pos.code}
            orders = mirror_orders(st["positions"], pos, {s: latest_price(s, "US", "etf") for s in syms})
            print(sync_orders(b, orders, PAPER_DIR / f"{a.sync}.csv", a.force))
        finally:
            b.close()
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
