"""份额净值账本：两个账户合并的人民币净值按份额（时间加权）记录，入金/出金不改变净值；合并回撤到 -15% 提醒复盘，-50% 提醒触及上限（2026-11-06 起；2026-11-04 起 -30%，之前 -20%）。只提醒，不交易。"""
import subprocess
from pathlib import Path

import pandas as pd

LEDGER = Path("live/nav.csv")
FLOWS = Path("config/flows.csv")
REVIEW, LIMIT = -0.15, -0.50  # -15% 只提醒复盘（2026-10-31）；上限 -50%（2026-11-06 换激进版（-50%））
STALE_DAYS = 5
CCYS = ("USD", "CNY", "AUD")
COLS = ["date", "value_cny", "flow_cny", "units", "nav", "price_date", *(f"booked_{c}" for c in CCYS)]


def record(ledger: pd.DataFrame | None, day: pd.Timestamp, value_cny: float, flow_cny: float,
           price_date: pd.Timestamp | None = None, booked: dict | None = None) -> pd.DataFrame:
    """追加一天；首行 units = 市值、nav = 1；之后按前一天净值把当天现金流换成份额。同一天重复记录时替换。"""
    led = pd.DataFrame(columns=COLS) if ledger is None else ledger[ledger.date < day]
    if len(led) == 0:
        units, flow_cny = value_cny, 0.0
    else:
        prev = led.iloc[-1]
        units = prev.units + flow_cny / prev.nav
    row = {"date": day, "value_cny": value_cny, "flow_cny": flow_cny, "units": units, "nav": value_cny / units,
           "price_date": price_date if price_date is not None else day,
           **{f"booked_{c}": (booked or {}).get(c, 0.0) for c in CCYS}}
    return pd.concat([led, pd.DataFrame([row])], ignore_index=True) if len(led) else pd.DataFrame([row])


def drawdown(ledger: pd.DataFrame) -> float:
    nav = ledger.nav.astype(float)
    return float(nav.iloc[-1] / nav.cummax().iloc[-1] - 1)


def alert_level(dd: float) -> str:
    if dd <= LIMIT + 1e-12:
        return "触及上限"
    if dd <= REVIEW + 1e-12:
        return "复盘提醒"
    return "正常"


def should_record(price_date: pd.Timestamp, today: pd.Timestamp) -> bool:
    """最旧价格超过 5 天就不记，避免用过期价格冒充今天。"""
    return (today.normalize() - price_date.normalize()).days <= STALE_DAYS


def _to_cny(amount: float, ccy: str, fx_last: dict) -> float:
    """fx_last：1 澳元能换多少该货币。"""
    return amount / fx_last[ccy] * fx_last["CNY"]


def portfolio_value_cny(holdings: pd.DataFrame, quotes: dict, fx_last: dict) -> tuple[float, pd.Timestamp]:
    """合并人民币市值和最旧的价格日期。quotes：{代码: (日期, 价格)}。"""
    v = 0.0
    for r in holdings.itertuples():
        local = r.shares if r.symbol == "CASH" else r.shares * quotes[r.symbol][1]
        v += _to_cny(local, r.ccy, fx_last)
    return v, min(q[0] for q in quotes.values())


def flows_between(flows: pd.DataFrame, after: pd.Timestamp | None, upto: pd.Timestamp, fx_last: dict) -> float:
    """(after, upto] 之间的入金（正）/出金（负），换算成人民币。"""
    d = pd.to_datetime(flows.date)
    m = (d <= upto) if after is None else (d > after) & (d <= upto)
    return float(sum(_to_cny(r.amount, r.ccy, fx_last) for r in flows[m].itertuples()))


def booked_of(ledger: pd.DataFrame | None, before: pd.Timestamp) -> dict | None:
    """today 之前最后一行已入账的各币种现金流累计；没有记录时返回 None。"""
    if ledger is None:
        return None
    prev = ledger[ledger.date < before]
    if prev.empty:
        return None
    last = prev.iloc[-1]
    return {c: float(last[f"booked_{c}"]) if pd.notna(last.get(f"booked_{c}")) else 0.0 for c in CCYS}


def pending_flows(flows: pd.DataFrame, booked: dict, upto: pd.Timestamp, fx_last: dict) -> tuple[dict, float]:
    """flows.csv 里日期 ≤ upto 的各币种累计，减去已入账累计，差额换成人民币作为本次现金流。
    这样当天 9:00 之后才录入的、补录过去日期的、或碰上价格过期跳过的现金流都不会丢。"""
    d = pd.to_datetime(flows.date)
    f = flows[d <= upto]
    totals = {c: float(f[f.ccy == c].amount.sum()) for c in CCYS}
    return totals, sum(_to_cny(totals[c] - booked.get(c, 0.0), c, fx_last) for c in CCYS)


def load_ledger(path: Path = LEDGER) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["date", "price_date"])


def notify(title: str, msg: str) -> None:
    """macOS 通知；失败不影响记账。"""
    try:
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "{title}"'],
                       check=False, timeout=10, capture_output=True)
    except Exception:
        pass


def render_daily(led: pd.DataFrame, level: str, note: str = "") -> str:
    last = led.iloc[-1]
    return "\n".join([
        f"# 每日净值 {last.date:%Y-%m-%d}", "",
        f"- 合并市值：{last.value_cny:,.0f} 元（价格日期 {pd.Timestamp(last.price_date):%Y-%m-%d}）",
        f"- 份额净值：{last.nav:.4f}；当天入金/出金 {last.flow_cny:,.0f} 元",
        f"- 合并回撤（从记账以来最高点）：{drawdown(led) * 100:.1f}%",
        f"- 状态：**{level}**" + ("（-15%：停下来复盘，不自动交易）" if level == "复盘提醒" else
                                (f"（{LIMIT * 100:.0f}%：已到你设的实盘上限，请复盘并决定下一步）" if level == "触及上限" else "")),
        *([f"- {note}"] if note else []), "",
        "> 声明：本记录只是系统计算的数字，不是投资建议。", ""])


def main() -> int:
    import warnings
    for cat in (FutureWarning, DeprecationWarning, pd.errors.PerformanceWarning):
        warnings.filterwarnings("ignore", category=cat)
    from quant.data.update import get_price, latest_quote
    from quant.portfolio.holdings import load_holdings
    from quant.research.p5 import STOCKS

    today = pd.Timestamp.today().normalize()
    fx = {"AUDUSD": get_price("AUDUSD", "FX", "fx"), "AUDCNY": get_price("AUDCNY", "FX", "fx")}
    fx_last = {"USD": float(fx["AUDUSD"].iloc[-1]), "CNY": float(fx["AUDCNY"].iloc[-1]), "AUD": 1.0}
    h = load_holdings()
    quotes = {r.symbol: latest_quote(r.symbol, r.market, "stock" if r.symbol in STOCKS else "etf")
              for r in h.itertuples() if r.symbol != "CASH"}
    value, pdate = portfolio_value_cny(h, quotes, fx_last)
    if not should_record(pdate, today):
        print(f"价格可能过期（最旧 {pdate:%Y-%m-%d}），今天不记账。")
        return 1
    led = load_ledger()
    flows = pd.read_csv(FLOWS) if FLOWS.exists() else pd.DataFrame(columns=["date", "account", "amount", "ccy", "note"])
    booked = booked_of(led, today)
    totals, flow = pending_flows(flows, booked or {}, today, fx_last)
    if booked is None:  # 第一行：之前的现金流已含在起始市值里
        flow = 0.0
    led = record(led, today, value, flow, pdate, totals)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    led.to_csv(LEDGER, index=False)
    level = alert_level(drawdown(led))
    out = LEDGER.parent / f"daily-{today:%Y-%m-%d}.md"
    out.write_text(render_daily(led, level))
    if level != "正常":
        notify("组合回撤" + level, f"合并回撤 {drawdown(led) * 100:.1f}%，请看 {out}")
    print(f"已记账：{today:%Y-%m-%d} 市值 {value:,.0f} 元，净值 {led.nav.iloc[-1]:.4f}，回撤 {drawdown(led) * 100:.1f}%，{level}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
