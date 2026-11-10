import json
from pathlib import Path

from quant.live import plan


def test_plan_matches_research_pick():
    pick = json.loads(Path("research/aggr_pick.json").read_text())["pick"]
    assert plan.trial_names() == tuple(pick)


def test_plan_is_aggr_50():
    # 2026-11-06 用户决定换成 -50% 上限下选中的方案
    assert plan.account("美股账户")["eq"] == ["QLD"]
    assert plan.account("A股账户")["eq"] == ["512100"]
    assert plan.core("美股账户") == (0.8, "债金1比1", "static")
    assert plan.core("A股账户") == (0.8, "债金1比1", "sma10_bond")
