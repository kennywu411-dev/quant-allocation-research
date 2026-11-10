"""当前实盘使用的方案（唯一来源）。换方案只改这里。
2026-11-06 用户决定替换为激进版（-50%）（见 reports/激进版-方案-2026-11-05.md）；
之前：2026-11-04 起激进版（QQQ 90% + A股防守配置，上限 -30%）；再之前 P5 方案（SPY 60% / A股 30%，均线）。"""
import pandas as pd

from quant.research import aggr, p3

NAME, SINCE = "激进版（-50%）", "2026-11-06"
LABELS = ("美股账户", "A股账户")
# sleeve=None 表示用 P3 原账户配置（A股：510300 + 510880）
SPEC = {"美股账户": {"sleeve": "QLD", "e": 0.8, "split": "债金1比1", "signal": "static"},
        "A股账户": {"sleeve": "512100", "e": 0.8, "split": "债金1比1", "signal": "sma10_bond"}}


def core(label: str) -> tuple[float, str, str]:
    s = SPEC[label]
    return s["e"], s["split"], s["signal"]


def account(label: str) -> dict:
    s = SPEC[label]
    return aggr.account_cfg(label, s["sleeve"]) if s["sleeve"] else p3.ACCOUNTS[label]


def trial_names() -> tuple[str, str]:
    """和研究登记表里的试验名称对应，用来核对实盘配置就是研究选中的那一个。"""
    def name(label: str) -> str:
        s = SPEC[label]
        if s["sleeve"]:
            return aggr.trial_name(label, s["sleeve"], s["e"], s["signal"])
        return f"P3｜{label}｜股{int(round(s['e'] * 100))}%｜{s['split']}｜{s['signal']}"
    return name("美股账户"), name("A股账户")


def default_getters(get_price) -> dict:
    """代理序列的取数函数，和研究网格、方案报告用的同一套（中证指数、2 倍杠杆合成）。"""
    from quant.data.update import get_csindex, get_french
    from quant.research.aggr_data import SYNTH_FEE, leveraged
    rf = get_french("F-F_Research_Data_Factors_daily", "RF").pct_change()
    return {"csindex": get_csindex, "french": lambda code: get_french(*code.split(":")),
            "lev": lambda code: leveraged(get_price(code, "US", "etf"), 2, SYNTH_FEE, rf)}


def build(label: str, get_price, get_index, fx: dict, getters: dict | None = None) -> tuple[dict, pd.DataFrame]:
    s = SPEC[label]
    if s["sleeve"]:
        g = getters if getters is not None else default_getters(get_price)
        a, px, _ = aggr.sleeve_setup(label, s["sleeve"], get_price, get_index, fx, g)
        return a, px
    a = p3.ACCOUNTS[label]
    return a, p3.build_prices(a, get_price, get_index, fx, getters)[0]
