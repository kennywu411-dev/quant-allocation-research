"""取数：yfinance（美股、汇率）、AKShare 优先 + BaoStock 兜底（A股）。返回复权收盘价序列。"""
from typing import Literal

import pandas as pd


class DataSourceError(RuntimeError):
    pass


def _clean(s: pd.Series, name: str, source: str) -> pd.Series:
    s = pd.Series(s.astype(float).values, index=pd.to_datetime(s.index).tz_localize(None), name=name)
    s = s.sort_index().dropna()
    s = s[~s.index.duplicated(keep="last")]
    s.attrs["source"] = source
    return s


def _yf_close(symbol: str, start: str) -> pd.Series:
    import yfinance as yf

    df = yf.Ticker(symbol).history(start=start, auto_adjust=True)
    if df.empty:
        raise DataSourceError(f"{symbol}: yfinance 返回空数据")
    return df["Close"]


def fetch_us(ticker: str, start: str) -> pd.Series:
    try:
        return _clean(_yf_close(ticker, start), ticker, "yfinance")
    except DataSourceError:
        raise
    except Exception as e:
        raise DataSourceError(f"{ticker}: yfinance 失败：{e}") from e


def clean_spikes(s: pd.Series, threshold: float = 0.05) -> pd.Series:
    """抹平一日尖刺：当日跳动超过阈值、次日反向跳回原位（汇率数据坏点）。"""
    v = s.to_numpy(dtype=float, copy=True)
    for i in range(1, len(v) - 1):
        up = v[i] / v[i - 1] - 1
        back = v[i + 1] / v[i] - 1
        if abs(up) > threshold and abs(back) > threshold and up * back < 0 and abs(v[i + 1] / v[i - 1] - 1) < threshold / 2:
            v[i] = v[i - 1]
    return pd.Series(v, index=s.index, name=s.name)


def fetch_fx(pair: Literal["AUDUSD", "AUDCNY"], start: str) -> pd.Series:
    try:
        s = clean_spikes(_clean(_yf_close(f"{pair}=X", start), pair, "yfinance"))
        s.attrs["source"] = "yfinance（已清洗一日尖刺）"
        return s
    except Exception as e:
        raise DataSourceError(f"{pair}: 汇率获取失败：{e}") from e


def _cn_akshare(code: str, start: str, kind: str, adjust: str = "hfq") -> pd.Series:
    import akshare as ak

    s = start.replace("-", "")
    if kind == "etf":
        df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date=s, end_date="20991231", adjust=adjust)
    else:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=s, end_date="20991231", adjust=adjust)
    if df is None or df.empty:
        raise DataSourceError(f"{code}: AKShare 返回空数据")
    return pd.Series(df["收盘"].values, index=pd.to_datetime(df["日期"]))


def _cn_baostock(code: str, start: str, kind: str, adjust: str = "hfq") -> pd.Series:
    import baostock as bs

    prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    bs.login()
    try:
        rs = bs.query_history_k_data_plus(f"{prefix}.{code}", "date,close", start_date=start,
                                          frequency="d", adjustflag="1" if adjust == "hfq" else "3")
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
    finally:
        bs.logout()
    if not rows:
        raise DataSourceError(f"{code}: BaoStock 返回空数据")
    df = pd.DataFrame(rows, columns=["date", "close"])
    df = df[df["close"] != ""]
    return pd.Series(df["close"].astype(float).values, index=pd.to_datetime(df["date"]))


def fetch_cn(code: str, start: str, kind: Literal["stock", "etf"], adjust: str = "hfq") -> pd.Series:
    """adjust="hfq" 用于算收益；adjust="" 是实际成交价，用于算当前市值。"""
    errors = []
    for name, fn in (("akshare", _cn_akshare), ("baostock", _cn_baostock)):
        try:
            return _clean(fn(code, start, kind, adjust), code, name)
        except Exception as e:
            errors.append(f"{name}: {e}")
    raise DataSourceError(f"{code}: 所有数据源都失败 — " + "; ".join(errors))


def _idx_akshare(code: str, start: str) -> pd.Series:
    import akshare as ak

    df = ak.stock_zh_index_daily(symbol=code)
    s = pd.Series(df["close"].values, index=pd.to_datetime(df["date"]))
    return s.loc[start:]


def _idx_baostock(code: str, start: str) -> pd.Series:
    import baostock as bs

    bs.login()
    try:
        rs = bs.query_history_k_data_plus(f"{code[:2]}.{code[2:]}", "date,close", start_date=start, frequency="d")
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
    finally:
        bs.logout()
    if not rows:
        raise DataSourceError(f"{code}: BaoStock 返回空数据")
    df = pd.DataFrame(rows, columns=["date", "close"])
    return pd.Series(df["close"].astype(float).values, index=pd.to_datetime(df["date"]))


def fetch_cn_index(code: str, start: str) -> pd.Series:
    """A股指数（价格指数，不含分红），用于补齐 ETF 上市前的历史。code 形如 sh000300。"""
    errors = []
    for name, fn in (("akshare", _idx_akshare), ("baostock", _idx_baostock)):
        try:
            return _clean(fn(code, start), code, f"{name}（指数）")
        except Exception as e:
            errors.append(f"{name}: {e}")
    raise DataSourceError(f"{code}: 所有数据源都失败 — " + "; ".join(errors))


def fetch_csindex(code: str, start: str = "20000101") -> pd.Series:
    """中证指数官网收盘价（含全收益指数，如 H20269、H00300）。接口首行常是 2000-01-01 的占位行，剔除。"""
    import akshare as ak

    try:
        df = ak.stock_zh_index_hist_csindex(symbol=code, start_date=start,
                                            end_date=pd.Timestamp.today().strftime("%Y%m%d"))
    except Exception as e:
        raise DataSourceError(f"{code}: 中证指数接口失败：{e}") from e
    if df.empty:
        raise DataSourceError(f"{code}: 中证指数返回空数据")
    s = pd.Series(df["收盘"].values, index=pd.to_datetime(df["日期"]))
    s = s[s.index != pd.Timestamp("2000-01-01")]
    return _clean(s, code, "csindex")


FRENCH_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{}_CSV.zip"


def parse_french_csv(text: str) -> pd.DataFrame:
    """Ken French CSV：只取第一段（价值加权）。百分数转小数，-99.99/-999 视为缺失。"""
    lines, header, rows = text.splitlines(), None, []
    for line in lines:
        cells = [c.strip() for c in line.split(",")]
        if header is None:
            if len(cells) > 1 and cells[0] == "" and all(cells[1:]):
                header = cells[1:]
            continue
        if not cells[0].isdigit():
            break
        rows.append(cells)
    if header is None or not rows:
        raise DataSourceError("French CSV 解析失败：找不到数据段")
    idx = pd.to_datetime([r[0] for r in rows], format="%Y%m%d" if len(rows[0][0]) == 8 else "%Y%m")
    df = pd.DataFrame([[float(x) for x in r[1:]] for r in rows], index=idx, columns=header)
    return df.mask(df <= -99.99) / 100


def french_to_price(r: pd.Series) -> pd.Series:
    return (1 + r.dropna()).cumprod()


def fetch_french(dataset: str, column: str) -> pd.Series:
    """French 组合日收益转成从 1 开始的累计价格；column='MKT' 表示 Mkt-RF + RF。"""
    import io
    import urllib.request
    import zipfile

    try:
        raw = urllib.request.urlopen(FRENCH_URL.format(dataset), timeout=60).read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        df = parse_french_csv(z.read(z.namelist()[0]).decode("latin-1"))
    except DataSourceError:
        raise
    except Exception as e:
        raise DataSourceError(f"French {dataset}: 下载失败：{e}") from e
    r = df["Mkt-RF"] + df["RF"] if column == "MKT" else df[column]
    return _clean(french_to_price(r), f"{dataset}:{column}", "kenfrench")
