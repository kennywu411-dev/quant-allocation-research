"""本地缓存：data/cache/tushare/<接口>/<键>.parquet。
键：按交易日的接口是 YYYYMMDD；财务接口是 <报告期>_rt<report_type>；业绩预告是 <报告期>。"""
import os
from pathlib import Path

import pandas as pd

ROOT = Path("data/cache/tushare")


def path(api: str, key: str, root: Path = ROOT) -> Path:
    return root / api / f"{key}.parquet"


def exists(api: str, key: str, root: Path = ROOT) -> bool:
    return path(api, key, root).exists()


def write(api: str, key: str, df: pd.DataFrame, root: Path = ROOT) -> Path:
    """先写临时文件再改名：中途被打断不会留下半个 parquet。"""
    p = path(api, key, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    df = df.copy()
    for c in df.columns:  # 整列为空的 object 列统一成字符串，避免各分片 schema 不一致
        if df[c].dtype == object and df[c].isna().all():
            df[c] = df[c].astype("string")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, p)
    return p


def keys(api: str, root: Path = ROOT) -> list[str]:
    d = root / api
    return sorted(p.stem for p in d.glob("*.parquet")) if d.exists() else []


def load(api: str, start: str | None = None, end: str | None = None, columns: list[str] | None = None,
         root: Path = ROOT) -> pd.DataFrame:
    """把一个接口的分片拼起来。start/end 按键的前 8 位（YYYYMMDD）筛选，两端都包含。"""
    ks = [k for k in keys(api, root) if (start is None or k[:8] >= start) and (end is None or k[:8] <= end)]
    parts = []
    for k in ks:
        df = pd.read_parquet(path(api, k, root), columns=columns)
        if len(df):
            parts.append(df)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns or [])
