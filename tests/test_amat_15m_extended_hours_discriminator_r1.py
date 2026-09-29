from __future__ import annotations

from datetime import datetime, timezone
from research.amat_15m_extended_hours_discriminator_r1 import summarize

class Bar:
    def __init__(self, value):
        self.date = value

def dt(hour, minute):
    return datetime(2026, 6, 15, hour, minute, tzinfo=timezone.utc)

def test_summarize_separates_extended_and_rth_clock_bars():
    bars=[Bar(dt(8,0)),Bar(dt(13,30)),Bar(dt(15,0)),Bar(dt(20,0)),Bar(dt(23,0))]
    out=summarize(bars,target_date="2026-06-15")
    assert out["bar_count"] == 5
    assert out["rth_clock_count"] == 2
    assert out["extended_clock_count"] == 3
    assert out["first_bar_time_et"].endswith("-04:00")

def test_summarize_filters_other_dates():
    bars=[Bar(datetime(2026,6,14,15,0,tzinfo=timezone.utc)),Bar(dt(15,0))]
    out=summarize(bars,target_date="2026-06-15")
    assert out["bar_count"] == 1
