import pandas as pd
import pytest

import quant.live.moomoo_paper as mp
from quant.live.moomoo_paper import PaperBroker, sync_orders, to_code


@pytest.fixture(autouse=True)
def _fake_acc_id(monkeypatch):
    """测试不依赖私有的账户号文件。"""
    monkeypatch.setattr(mp, "PAPER_ACC_ID", 999001)


class Fake:
    def __init__(self):
        self.calls = []

    def _rec(self, name, kw, df):
        self.calls.append((name, kw.get("trd_env")))
        return 0, df

    def position_list_query(self, **kw):
        return self._rec("pos", kw, pd.DataFrame({"code": ["US.SPY"], "qty": [3.0], "cost_price": [700.0]}))

    def accinfo_query(self, **kw):
        return self._rec("acc", kw, pd.DataFrame({"cash": [1000.0]}))

    def place_order(self, price, qty, code, trd_side, **kw):
        self.placed = (price, qty, code, trd_side)
        return self._rec("place", kw, pd.DataFrame({"order_id": ["A1"]}))

    def modify_order(self, op, order_id, qty, price, **kw):
        return self._rec("cancel", kw, pd.DataFrame({"order_id": [order_id]}))

    def order_list_query(self, **kw):
        return self._rec("orders", kw, pd.DataFrame({"order_id": ["A1"], "code": ["US.SPY"], "trd_side": ["BUY"],
                                                     "qty": [10.0], "price": [700.0], "order_status": ["FILLED_PART"],
                                                     "dealt_qty": [3.0], "dealt_avg_price": [699.5]}))


def test_real_env_refused():
    with pytest.raises(ValueError, match="只允许模拟盘"):
        PaperBroker(client=Fake(), env="REAL")


def test_trade_calls_use_simulate():
    f = Fake()
    b = PaperBroker(client=f)
    b.positions(); b.cash(); b.place_limit("SPY", "买", 1, 500.0); b.cancel("A1"); b.orders()
    assert {e for _, e in f.calls} == {"SIMULATE"}
    assert len(f.calls) == 5


def test_partial_fill_recorded():
    o = PaperBroker(client=Fake()).orders()
    assert o.dealt_qty.iloc[0] == 3 and o.qty.iloc[0] == 10
    assert o.status.iloc[0] == "FILLED_PART"


def test_symbol_prefix():
    assert to_code("SPY") == "US.SPY"
    assert to_code("US.SPY") == "US.SPY"


def test_sync_orders_limit_band(tmp_path):
    f = Fake()
    orders = pd.DataFrame([{"symbol": "SPY", "side": "买", "shares": 2, "price": 100.0, "value": 200.0, "cost": 1.0},
                           {"symbol": "CASH", "side": "剩余", "shares": 0, "price": 1.0, "value": 5.0, "cost": 0.0}])
    log = sync_orders(PaperBroker(client=f), orders, tmp_path / "p.csv")
    assert f.placed[0] == pytest.approx(100.5) and f.placed[1] == 2 and f.placed[2] == "US.SPY"
    assert list(log.order_id) == ["A1"]
    assert (tmp_path / "p.csv").exists()


def test_history_orders_simulate():
    f = Fake()
    f.history_order_list_query = lambda **kw: f._rec("hist", kw, f.order_list_query(trd_env="SIMULATE")[1])
    o = PaperBroker(client=f).history_orders("2026-11-01", "2026-11-30")
    assert o.status.iloc[0] == "FILLED_PART"
    assert {e for _, e in f.calls} == {"SIMULATE"}


def test_sync_refuses_second_run(tmp_path):
    orders = pd.DataFrame([{"symbol": "SPY", "side": "买", "shares": 2, "price": 100.0, "value": 200.0, "cost": 1.0}])
    sync_orders(PaperBroker(client=Fake()), orders, tmp_path / "p.csv")
    with pytest.raises(FileExistsError):
        sync_orders(PaperBroker(client=Fake()), orders, tmp_path / "p.csv")


def test_mirror_orders_never_short():
    from quant.live.moomoo_paper import mirror_orders
    paper = pd.DataFrame({"code": ["US.IEF", "US.MU"], "qty": [62.0, 0.0]})
    o = mirror_orders({"SPY": 14, "IEF": 61, "TLT": 23}, paper, {"SPY": 750.0, "IEF": 91.0, "TLT": 81.0})
    got = {(r.symbol, r.side): r.shares for r in o.itertuples()}
    assert got == {("IEF", "卖"): 1, ("SPY", "买"): 14, ("TLT", "买"): 23}
    assert list(o.side[:1]) == ["卖"]  # 先卖后买


def test_mirror_orders_sells_only_held():
    from quant.live.moomoo_paper import mirror_orders
    paper = pd.DataFrame({"code": ["US.GLD"], "qty": [5.0]})
    o = mirror_orders({}, paper, {"GLD": 300.0})
    assert list(zip(o.symbol, o.side, o.shares)) == [("GLD", "卖", 5)]


def test_paper_acc_id_sources(tmp_path):
    from quant.live.moomoo_paper import paper_acc_id
    f = tmp_path / "id.txt"
    assert paper_acc_id({}, f) == 0
    f.write_text("123\n")
    assert paper_acc_id({}, f) == 123 and paper_acc_id({"MOOMOO_PAPER_ACC_ID": "456"}, f) == 456


def test_pinned_paper_account(monkeypatch):

    class F(Fake):
        def _rec(self, name, kw, df):
            self.calls.append((name, kw.get("trd_env"), kw.get("acc_id")))
            return 0, df
    f = F()
    b = PaperBroker(client=f)
    b.positions(); b.cash(); b.place_limit("SPY", "买", 1, 500.0); b.cancel("A1"); b.orders()
    assert {a for _, _, a in f.calls} == {999001}
    monkeypatch.setattr(mp, "PAPER_ACC_ID", 0)
    with pytest.raises(ValueError):
        PaperBroker(client=f)
