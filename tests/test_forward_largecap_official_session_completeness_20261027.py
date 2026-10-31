"""Source-only falsifier: common-mode missing official sessions cannot compress fixed20."""
from __future__ import annotations

import exchange_calendars as xc
import pandas as pd
import pytest

from research.forward_largecap_transport_observer_r1 import _common_calendar, _first_entry

SYMBOLS = ("CAT", "JPM", "UNH", "XOM", "COST", "MSFT", "SPY", "QQQ")


def sessions() -> pd.DatetimeIndex:
    return xc.get_calendar("XNYS").sessions_in_range(
        "2026-09-11", "2026-10-20"
    ).tz_localize(None)


def panel(index: pd.DatetimeIndex) -> dict[str, pd.Series]:
    return {
        symbol: pd.Series([100.0 + i for i in range(len(index))], index=index)
        for symbol in SYMBOLS
    }


def test_complete_official_calendar_is_preserved():
    expected = sessions()
    assert len(expected) == 28
    actual = _common_calendar(panel(expected), list(SYMBOLS))
    assert actual.equals(expected)


def test_synchronized_missing_official_session_fails_closed():
    expected = sessions()
    sparse = expected.drop(pd.Timestamp("2026-09-15"))
    # Every source agrees, so the former equality-only gate passed.
    assert all(series.index.equals(sparse) for series in panel(sparse).values())
    entry_official = _first_entry(expected, "2026-09-11", 1)
    entry_sparse = _first_entry(sparse, "2026-09-11", 1)
    assert entry_official[1] == entry_sparse[1] == pd.Timestamp("2026-09-14")
    assert expected[entry_official[0] + 20] == pd.Timestamp("2026-10-12")
    assert sparse[entry_sparse[0] + 20] == pd.Timestamp("2026-10-13")
    with pytest.raises(RuntimeError, match="SOURCE_CALENDAR_INCOMPLETE"):
        _common_calendar(panel(sparse), list(SYMBOLS))


def test_asymmetric_missing_session_still_fails_closed():
    expected = sessions()
    prices = panel(expected)
    prices["CAT"] = prices["CAT"].drop(pd.Timestamp("2026-09-15"))
    with pytest.raises(RuntimeError, match="SOURCE_CALENDAR_INCOMPLETE"):
        _common_calendar(prices, list(SYMBOLS))


def test_common_mode_unexpected_nonexchange_date_fails_closed():
    expected = sessions()
    unexpected = expected.union(pd.DatetimeIndex(["2026-09-12"]))
    with pytest.raises(RuntimeError, match="SOURCE_CALENDAR_INCOMPLETE"):
        _common_calendar(panel(unexpected), list(SYMBOLS))
