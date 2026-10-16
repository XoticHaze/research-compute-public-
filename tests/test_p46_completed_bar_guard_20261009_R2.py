"""Pre-outcome source regression for the selected P46 completed-bar guard."""
from __future__ import annotations
import pandas as pd
from research.p46_forward_observer_r2 import U, _common_close_panel


def _bars():
    rows = []
    for day in ("2026-10-07", "2026-10-08"):
        for symbol in U:
            rows.append({"symbol": symbol, "timestamp": pd.Timestamp(day, tz="UTC"), "close": 100.0})
    return pd.DataFrame(rows)


def test_delayed_preopen_run_does_not_admit_partial_daily_bar():
    px = _common_close_panel(_bars(), pd.Timestamp("2026-10-08T18:09:57Z"))
    assert str(px.index.max().date()) == "2026-10-07"


def test_post_settlement_admits_complete_day():
    px = _common_close_panel(_bars(), pd.Timestamp("2026-10-09T01:18:51Z"))
    assert str(px.index.max().date()) == "2026-10-08"


def test_post_settlement_provider_lag_stays_on_last_common_session():
    x = _bars()
    x = x[~((x.symbol == U[0]) & (x.timestamp == pd.Timestamp("2026-10-08", tz="UTC")))]
    px = _common_close_panel(x, pd.Timestamp("2026-10-09T01:18:51Z"))
    assert str(px.index.max().date()) == "2026-10-07"


def test_post_close_cron_in_dst_and_standard_time():
    from research.p46_forward_observer_r2 import _completed_market_data_date
    assert str(_completed_market_data_date(pd.Timestamp("2026-10-08T21:30:00Z").to_pydatetime())) == "2026-10-08"
    assert str(_completed_market_data_date(pd.Timestamp("2027-01-08T21:30:00Z").to_pydatetime())) == "2027-01-08"
