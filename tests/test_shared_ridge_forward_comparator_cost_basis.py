"""Synthetic-only cost-basis contract for Shared Ridge forward cohort reporting.

No market-data access, new model signal, scientific promotion, or broker action.
Legacy mixed-cost fields stay readable but must be explicitly labeled; only
the separately named net-vs-net comparators are after-cost comparisons.
"""
from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from forward_prospective_cohort_ledger_r1 import (
    _expression_variant_metrics,
    _resolve_semiconductor,
)


def _synthetic_case(n_sessions=25):
    days = pd.bdate_range("2026-09-11", periods=n_sessions, tz="UTC")
    def series(final):
        return pd.Series([100.0 if i < 21 else final for i in range(n_sessions)], index=days)
    prices = {"AAA": series(110.0), "SMH": series(105.0), "QQQ": series(104.0)}
    cohort = {
        "program_id": "SEMICONDUCTOR_SHARED_RIDGE",
        "signal_date": "2026-09-11",
        "first_registered_at": "2026-09-11T12:00:00Z",
        "execution_delay_sessions": 1,
        "holding_horizon_sessions": 20,
        "symbols": ["AAA"],
        "ticker_book_weights_within_cohort": {"AAA": 1.0},
        "stock_round_trip_cost_bps": 25.0,
        "industry_round_trip_cost_bps": 10.0,
        "predicted_fixed20_net_value_bps": {"AAA": 800.0},
    }
    return cohort, prices


def test_resolved_cohort_preserves_legacy_but_labels_matched_after_cost():
    cohort, prices = _synthetic_case()
    result = _resolve_semiconductor(cohort, prices, is_new=False)
    assert result["status"] == "RESOLVED"
    r = result["resolution"]
    assert r["ticker_book_net_return_bps"] == pytest.approx(975.0)
    assert r["benchmarks"]["smh_buy_and_hold_return_bps"] == pytest.approx(500.0)
    assert r["benchmarks"]["smh_buy_and_hold_net_return_bps"] == pytest.approx(490.0)
    assert r["ticker_book_excess_vs_smh_bps"] == pytest.approx(475.0)
    assert r["ticker_book_excess_vs_smh_net_bps"] == pytest.approx(485.0)
    assert r["comparison_cost_basis"]["ticker_book_excess_vs_smh_bps"].startswith("MIXED_")
    assert r["comparison_cost_basis"]["ticker_book_excess_vs_smh_net_bps"].startswith("MATCHED_")
    assert "NO_QQQ_FEE" in r["comparison_cost_basis"]["ticker_book_excess_vs_qqq_bps"]
    assert r["ticker_book_excess_vs_equal_weight_13_net_bps"] == pytest.approx(0.0)


def test_open_cohort_has_explicit_net_if_flattened_now_comparators():
    cohort, prices = _synthetic_case(n_sessions=10)
    result = _resolve_semiconductor(cohort, prices, is_new=False)
    assert result["status"] == "OPEN"
    r = result["resolution"]["current_mark_metrics"]
    assert r["ticker_book_net_if_flattened_now_bps"] == pytest.approx(-25.0)
    assert r["smh_return_bps"] == pytest.approx(0.0)
    assert r["smh_net_if_flattened_now_bps"] == pytest.approx(-10.0)
    assert r["ticker_book_matched_excess_vs_smh_bps"] == pytest.approx(-25.0)
    assert r["ticker_book_matched_excess_vs_smh_net_if_flattened_now_bps"] == pytest.approx(-15.0)
    assert r["ticker_book_excess_vs_equal_weight_universe_net_if_flattened_now_bps"] == pytest.approx(0.0)
    assert r["comparison_cost_basis"]["ticker_book_matched_excess_vs_smh_bps"].startswith("MIXED_")
    assert r["comparison_cost_basis"]["ticker_book_matched_excess_vs_smh_net_if_flattened_now_bps"].startswith("MATCHED_")


def test_expression_variants_keep_gross_benchmark_distinct_from_net():
    cohort, _ = _synthetic_case()
    cohort["expression_variants"] = {
        "incumbent_frozen_book": {
            "weights_within_cohort": {"AAA": 1.0},
            "scientific_forward_credit": True,
        }
    }
    variant = _expression_variant_metrics(cohort, {"AAA": 1000.0}, 500.0, 400.0, 1000.0, 25.0)
    r = variant["incumbent_frozen_book"]
    assert r["excess_vs_smh_bps"] == pytest.approx(475.0)
    assert r["excess_vs_smh_net_bps"] == pytest.approx(485.0)
    assert r["comparison_cost_basis"]["excess_vs_smh_bps"].startswith("MIXED_")
    assert r["comparison_cost_basis"]["excess_vs_smh_net_bps"].startswith("MATCHED_")
    assert "NO_QQQ_FEE" in r["comparison_cost_basis"]["excess_vs_qqq_bps"]
