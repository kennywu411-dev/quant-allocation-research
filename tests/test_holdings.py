import pandas as pd

from quant.portfolio.holdings import load_holdings


def test_load_holdings_cash_and_zero_code(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("account,market,symbol,shares,ccy,cost_basis,buy_date\n"
                 "a,US,CASH,100,USD,,\nb,CN,000651,1400,CNY,,\n")
    h = load_holdings(p)
    assert "000651" in h["symbol"].tolist()
    assert h["shares"].dtype == float
    assert pd.isna(h.loc[h.symbol == "000651", "cost_basis"]).all()
