"""读取用户持仓 CSV。现金行写作 symbol=CASH，shares 填金额。"""
from pathlib import Path

import pandas as pd

HOLDINGS_PATH = Path("config/holdings.csv")


def load_holdings(path: Path = HOLDINGS_PATH) -> pd.DataFrame:
    h = pd.read_csv(path, dtype=str)
    h["shares"] = pd.to_numeric(h["shares"], errors="coerce").astype(float)
    h["cost_basis"] = pd.to_numeric(h.get("cost_basis"), errors="coerce")
    if "note" not in h:
        h["note"] = ""
    h["note"] = h["note"].fillna("")
    return h
