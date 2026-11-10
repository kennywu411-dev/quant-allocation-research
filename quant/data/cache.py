"""本地 Parquet 缓存：每个序列一个 parquet 文件，加一个记录来源和抓取时间的 meta.json。"""
import json
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

DEFAULT_CACHE_DIR = Path("data/cache")


def _paths(key: str, cache_dir: Path) -> tuple[Path, Path]:
    return cache_dir / f"{key}.parquet", cache_dir / f"{key}.meta.json"


def _read(key: str, cache_dir: Path) -> tuple[pd.Series, dict]:
    data_path, meta_path = _paths(key, cache_dir)
    meta = json.loads(meta_path.read_text())
    s = pd.read_parquet(data_path).iloc[:, 0]
    s.name = key
    s.attrs["source"] = meta.get("source", "unknown")
    s.attrs["fetched_at"] = meta.get("fetched_at", "")
    s.attrs["stale"] = False
    return s, meta


def load_or_fetch(
    key: str,
    fetch: Callable[[], pd.Series],
    max_age_days: float = 1.0,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> pd.Series:
    cache_dir = Path(cache_dir)
    data_path, meta_path = _paths(key, cache_dir)
    cached = None
    if data_path.exists() and meta_path.exists():
        cached, meta = _read(key, cache_dir)
        age = datetime.now() - datetime.fromisoformat(meta["fetched_at"])
        if age <= timedelta(days=max_age_days):
            return cached
    try:
        s = fetch()
    except Exception as e:
        if cached is not None:
            warnings.warn(f"{key}: 更新失败（{e}），使用旧缓存", UserWarning)
            cached.attrs["stale"] = True
            return cached
        raise
    cache_dir.mkdir(parents=True, exist_ok=True)
    s = s.sort_index().dropna()
    s.index.name = "date"
    s.rename("value").to_frame().to_parquet(data_path)
    meta = {"source": s.attrs.get("source", "unknown"), "fetched_at": datetime.now().isoformat(timespec="seconds")}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False))
    out = s.copy()
    out.name = key
    out.attrs.update(meta, stale=False)
    return out
