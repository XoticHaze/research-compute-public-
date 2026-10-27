"""Synthetic-only forward bar timestamp source-admission regressions."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from research.forward_bar_contract_v2 import normalize_frame, ibkr_bar_to_record


def row(stamp):
    return {
        "symbol": "MNQ", "timestamp": stamp,
        "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0,
        "volume": 10, "source": "ibkr", "asset_type": "futures",
        "bar_size": "12Min", "session": "all", "contract_id": "MNQ-202612",
        "wap": 100.5, "bar_count": 5,
    }


@pytest.mark.parametrize("stamp", [
    "2026-10-26 09:30:00",
    "2026-10-26",
    datetime(2026, 10, 26, 9, 30),
    pd.Timestamp("2026-10-26 09:30:00"),
])
def test_naive_or_date_only_source_clock_never_becomes_utc(stamp):
    with pytest.raises(ValueError, match="explicit_timezone_required"):
        normalize_frame([row(stamp)])


def test_explicit_chicago_offset_normalizes_to_real_utc_instant():
    frame = normalize_frame([row("2026-10-26T09:30:00-05:00")])
    assert frame.iloc[0]["timestamp"] == pd.Timestamp("2026-10-26T14:30:00Z")


def test_explicit_utc_source_preserved():
    frame = normalize_frame([row(datetime(2026, 10, 26, 14, 30, tzinfo=timezone.utc))])
    assert frame.iloc[0]["timestamp"] == pd.Timestamp("2026-10-26T14:30:00Z")


def test_malformed_offset_looking_clock_fails_closed():
    with pytest.raises(ValueError, match="unparseable"):
        normalize_frame([row("not-a-date+00:00")])


def test_duplicate_instants_after_offset_normalization_still_rejected():
    with pytest.raises(ValueError, match="duplicate normalized bars"):
        normalize_frame([
            row("2026-10-26T09:30:00-05:00"),
            row("2026-10-26T14:30:00Z"),
        ])


def test_ibkr_adapter_does_not_invent_timezone_for_naive_bar():
    bar = SimpleNamespace(date=datetime(2026, 10, 26, 9, 30),
                          open=100, high=102, low=99, close=101,
                          volume=10, wap=100.5, barCount=5)
    contract = SimpleNamespace(conId=12345, localSymbol="MNQZ6")
    mapped = ibkr_bar_to_record(
        bar, contract, symbol="MNQ", asset_type="futures",
        bar_size="12Min", session="all",
    )
    with pytest.raises(ValueError, match="explicit_timezone_required"):
        normalize_frame([mapped])
