"""资产池配置与一键数据更新：python -m quant.data.update"""
from pathlib import Path

import pandas as pd

from quant.data.cache import load_or_fetch
from quant.data.sources import fetch_cn, fetch_cn_index, fetch_csindex, fetch_french, fetch_fx, fetch_us

UNIVERSE_PATH = Path("config/universe.csv")


def load_universe(path: Path = UNIVERSE_PATH) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str)


SPLIT_LOG: dict[str, list[tuple[pd.Timestamp, float]]] = {}  # 本次运行中做过份额拆分修正的标的
SPLIT_LIMIT = 0.30  # A股 ETF 单日涨跌幅上限 20%（创业板/科创）或 10%；超过 30% 只可能是数据源没调整的份额拆分/合并


def fix_splits(s: pd.Series, limit: float = SPLIT_LIMIT) -> tuple[pd.Series, list[tuple[pd.Timestamp, float]]]:
    """把超出涨跌停可能范围的单日跳变当作份额拆分：跳变当天收益记 0，之前的价格整体按跳变比例缩放（最新价不变）。"""
    s = s.dropna()
    r = s.pct_change()
    events = [(d, float(v)) for d, v in r[r.abs() > limit].items()]
    if not events:
        return s, []
    factor = pd.Series(1.0, index=s.index)
    for d, v in events:
        factor[s.index < d] *= 1 + v
    return s * factor, events


def split_notes() -> list[str]:
    return [f"{s}：数据源未调整份额拆分，按拆分修正了 " + "、".join(f"{d:%Y-%m-%d}（单日 {v:+.0%}）" for d, v in ev)
            for s, ev in SPLIT_LOG.items()]


def get_price(symbol: str, market: str, kind: str, start: str = "2002-01-01") -> pd.Series:
    if market == "US":
        fetch = lambda: fetch_us(symbol, start)
    elif market == "CN":
        fetch = lambda: fetch_cn(symbol, start, kind)
    elif market == "FX":
        fetch = lambda: fetch_fx(symbol, start)
    else:
        raise ValueError(f"{symbol}: 未知市场 {market}")
    s = load_or_fetch(symbol, fetch)
    if market == "CN" and kind == "etf":
        s, events = fix_splits(s)
        if events:
            SPLIT_LOG[symbol] = events
            import warnings
            warnings.warn(f"{symbol}：按份额拆分修正了 {len(events)} 处跳变：" +
                          "、".join(f"{d:%Y-%m-%d}（{v:+.0%}）" for d, v in events), stacklevel=2)
    return s


def get_index(code: str, start: str = "2002-01-01") -> pd.Series:
    return load_or_fetch(f"IDX_{code}", lambda: fetch_cn_index(code, start))


def get_csindex(code: str) -> pd.Series:
    return load_or_fetch(f"CSI_{code}", lambda: fetch_csindex(code))


def get_french(dataset: str, column: str) -> pd.Series:
    """French 数据每月更新一次，缓存 7 天。"""
    key = f"FF_{dataset}_{column}".replace(" ", "_").replace("-", "_")
    return load_or_fetch(key, lambda: fetch_french(dataset, column), max_age_days=7)


def latest_quote(symbol: str, market: str, kind: str) -> tuple[pd.Timestamp, float]:
    """当前实际价格及其日期。美股复权价的最新值就是实际价；A股后复权价不是，需另取不复权价。"""
    if market == "CN":
        start = (pd.Timestamp.today() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
        s = load_or_fetch(f"{symbol}_raw", lambda: fetch_cn(symbol, start, kind, adjust=""))
    else:
        s = get_price(symbol, market, kind)
    return s.index[-1], float(s.iloc[-1])


def latest_price(symbol: str, market: str, kind: str) -> float:
    return latest_quote(symbol, market, kind)[1]


def update_all() -> pd.DataFrame:
    rows = []
    for r in load_universe().itertuples():
        try:
            s = get_price(r.symbol, r.market, r.kind)
            rows.append({"symbol": r.symbol, "start": s.index[0].date(), "end": s.index[-1].date(),
                         "rows": len(s), "source": s.attrs.get("source", ""), "error": ""})
        except Exception as e:
            rows.append({"symbol": r.symbol, "start": None, "end": None, "rows": 0, "source": "", "error": str(e)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    with pd.option_context("display.width", 200, "display.max_colwidth", 80):
        print(update_all().to_string(index=False))
