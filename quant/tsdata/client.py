"""Tushare 调用封装：限速、重试、自动翻页。query 可注入，测试不联网。"""
import os
import threading
import time
from typing import Callable

import pandas as pd


class NoPermission(RuntimeError):
    """当前积分档位没有这个接口的权限。"""


class RateLimiter:
    """把调用均匀摊开：相邻两次至少间隔 60 / per_minute 秒。线程安全。"""

    def __init__(self, per_minute: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.interval = 60.0 / per_minute
        self._clock, self._sleep = clock, sleep
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            slot = max(now, self._next)
            self._next = slot + self.interval
        if slot > now:
            self._sleep(slot - now)


def _is_permission_error(msg: str) -> bool:
    return "权限" in msg and "每分钟" not in msg and "每天" not in msg and "每小时" not in msg


def _is_rate_error(msg: str) -> bool:
    return "每分钟" in msg or "每小时" in msg


class Client:
    def __init__(self, query: Callable[..., pd.DataFrame] | None = None, per_minute: float = 300,
                 retries: int = 4, sleep: Callable[[float], None] = time.sleep, limiter: RateLimiter | None = None):
        if query is None:
            token = os.environ.get("TUSHARE_TOKEN")
            if not token:
                raise SystemExit("环境变量 TUSHARE_TOKEN 未设置（先 source ~/.zshrc）")
            import tushare as ts
            query = ts.pro_api(token).query
        self._query = query
        self._sleep = sleep
        self.retries = retries
        self.limiter = limiter or RateLimiter(per_minute, sleep=sleep)
        self.calls = 0

    def _once(self, api: str, **params) -> pd.DataFrame:
        for attempt in range(self.retries + 1):
            self.limiter.wait()
            self.calls += 1
            try:
                df = self._query(api, **params)
                return df if df is not None else pd.DataFrame()
            except Exception as e:  # noqa: BLE001  tushare 只抛普通 Exception
                msg = str(e)
                if _is_permission_error(msg):
                    raise NoPermission(f"{api}: {msg[:120]}") from None
                if attempt == self.retries:
                    raise RuntimeError(f"{api} {params} 重试 {self.retries} 次仍失败：{msg[:160]}") from None
                self._sleep(61 if _is_rate_error(msg) else 3 * (attempt + 1))
        raise AssertionError("unreachable")

    def fetch(self, api: str, exhaustive: bool = False, **params) -> pd.DataFrame:
        """取一次请求的全部行。Tushare 的单次上限都是 100 的整数倍（实测 cashflow_vip 是 6400，其余 1000/3500/6000…），
        所以返回行数是 100 的非零整数倍时再用 offset 取下一页，直到某一页不是整数倍或为空。
        exhaustive=True 时不靠这个推断，一直翻到空页为止（财务接口用，多花一次调用换确定性）。"""
        parts, offset = [], 0
        while True:
            df = self._once(api, **params, **({"offset": offset} if offset else {}))
            if parts and df.equals(parts[-1]):  # 接口忽略了 offset，返回同一页：停止，防止死循环
                break
            if len(df):
                parts.append(df)
            if len(df) == 0 or (len(df) % 100 and not exhaustive):
                break
            offset += len(df)
        if not parts:
            return df
        out = pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
        return out.drop_duplicates(ignore_index=True) if len(parts) > 1 else out
