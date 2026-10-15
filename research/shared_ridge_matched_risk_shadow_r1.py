"""Read-only H20 Shared Ridge fixed-weight versus forecast-weight daily-path risk replay.

Scientific scope: historical diagnostic only. Predictions and pre-signal
volatility come exclusively from an already-frozen forward receipt. Market
prices are used solely to measure the completed 20-session holding path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

SCHEMA = "research.shared_ridge_matched_risk_shadow_r1"
PROGRAM = "SEMICONDUCTOR_SHARED_RIDGE"
COHORT = "SEMICONDUCTOR_SHARED_RIDGE:2026-09-11:aed8eb43d888d3c4"
ENTRY = "2026-09-14"
EXIT = "2026-10-12"
SIGNAL = "2026-09-11"
STOCK_COST_BPS = 25.0
SMH_COST_BPS = 10.0


def _finite(x, name, *, strictly_positive=True):
    try:
        y = float(x)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name}: finite number required") from exc
    if not math.isfinite(y) or (strictly_positive and y <= 0):
        raise ValueError(f"{name}: finite positive number required")
    return y


def _normalize(values, names):
    if set(values) != names:
        raise ValueError("comparison universe drift")
    weights = {s: _finite(values[s], s) for s in sorted(names)}
    den = sum(weights.values())
    return {s: weights[s] / den for s in sorted(names)}


def frozen_inputs(ledger, scoreboard):
    cohorts = [c for c in ledger.get("cohorts", []) if c.get("cohort_id") == COHORT]
    if len(cohorts) != 1:
        raise ValueError("one pinned prospective cohort required")
    c = cohorts[0]
    if c.get("program_id") != PROGRAM or c.get("signal_date") != SIGNAL or c.get("status") != "RESOLVED":
        raise ValueError("program/signal/status mismatch")
    r = c.get("resolution") or {}
    if (r.get("entry_date"), r.get("exit_date"), r.get("horizon_sessions")) != (ENTRY, EXIT, 20):
        raise ValueError("exact fixed20 resolution required")
    lanes = [l for l in scoreboard.get("lanes", []) if l.get("program_id") == PROGRAM]
    if len(lanes) != 1:
        raise ValueError("one source-linked scoreboard lane required")
    lane = lanes[0]
    if lane.get("signal_date") != SIGNAL:
        raise ValueError("scoreboard signal not pinned")
    b = (lane.get("paper_action") or {}).get("ticker_book") or {}
    if b.get("status") != "PAPER_COHORT_READY" or b.get("prediction_magnitude_used_for_sizing") is not False:
        raise ValueError("baseline paper sizing authority changed")
    timing = lane.get("timing") or {}
    if timing.get("execution_delay_sessions") != 1 or timing.get("holding_horizon_sessions") != 20:
        raise ValueError("frozen timing changed")
    if abs(_finite(timing.get("cohort_nav_fraction"), "cohort_nav_fraction") - 0.05) > 1e-10:
        raise ValueError("cohort budget changed")
    names = set(c.get("symbols") or [])
    if len(names) != 13 or names != set(lane.get("signal", {}).get("positive_symbols") or []):
        raise ValueError("exact thirteen-stock positive universe required")
    if names != set(c.get("ticker_book_weights_within_cohort") or {}):
        raise ValueError("frozen cohort weights incomplete")
    frozen = _normalize(c["ticker_book_weights_within_cohort"], names)
    scoreboard_w = b.get("cohort_target_weights_nav") or {}
    if set(scoreboard_w) != names or any(abs(scoreboard_w[s] - 0.05 * frozen[s]) > 1e-9 for s in names):
        raise ValueError("scoreboard/ledger frozen weight drift")
    vol = b.get("realized_vol20_annualized") or {}
    if set(vol) != names:
        raise ValueError("pre-signal volatility source missing")
    invvol = _normalize({s: 1 / _finite(vol[s], f"vol.{s}") for s in names}, names)
    if any(abs(invvol[s] - frozen[s]) > 1e-8 for s in names):
        raise ValueError("frozen inverse-vol reconstruction failure")
    preds = c.get("predicted_fixed20_net_value_bps") or {}
    if set(preds) != names:
        raise ValueError("pinned predictions incomplete")
    if any(abs(_finite(preds[s], f"prediction.{s}") - _finite(lane["signal"]["predicted_fixed20_net_value_bps"][s], s)) > 1e-6 for s in names):
        raise ValueError("forecast lineage drift")
    if set(r.get("ticker_observations") or {}) != names:
        raise ValueError("resolved return universe drift")
    variants = {
        "frozen_inverse_vol": frozen,
        "equal_weight": _normalize({s: 1 for s in names}, names),
        "forecast_proportional": _normalize(preds, names),
        "forecast_div_vol": _normalize({s: preds[s] / vol[s] for s in names}, names),
    }
    return c, r, variants


def compute(ledger, scoreboard, prices: pd.DataFrame, raw_close_prices: pd.DataFrame | None = None) -> dict:
    c, r, variants = frozen_inputs(ledger, scoreboard)
    symbols = sorted(variants["frozen_inverse_vol"])
    if not isinstance(prices, pd.DataFrame) or not set(symbols + ["SMH"]).issubset(set(prices.columns)):
        raise ValueError("whole cohort plus SMH price history required")
    p = prices[symbols + ["SMH"]].copy()
    p.index = pd.to_datetime(p.index).tz_localize(None).normalize()
    p = p.sort_index().loc[ENTRY:EXIT]
    if p.empty or p.index[0].date().isoformat() != ENTRY or p.index[-1].date().isoformat() != EXIT:
        raise ValueError("missing exact common entry/exit prices")
    if p.isna().any().any() or (p.astype(float) <= 0).any().any():
        raise ValueError("partial or nonpositive price path")
    if len(p) != 21 or p.index.has_duplicates:
        raise ValueError("expected exact 20 common-session holding intervals (21 closes)")
    p = p.astype(float)
    ratios = p[symbols].div(p[symbols].iloc[0]) - 1.0
    smh_gross = (p["SMH"].iloc[-1] / p["SMH"].iloc[0] - 1.0) * 10000
    if abs(smh_gross - _finite(r["benchmarks"]["smh_buy_and_hold_return_bps"], "SMH", strictly_positive=False)) > 8:
        raise ValueError("public adjusted-close SMH vs immutable benchmark drift")
    results = {}
    for name, weights in variants.items():
        gross_path = (ratios * pd.Series(weights)).sum(axis=1)
        # 12.5bp entry cost and 12.5bp exit cost; 25bp total matches ledger.
        equity = 1.0 + gross_path - STOCK_COST_BPS / 20000.0
        equity.iloc[-1] -= STOCK_COST_BPS / 20000.0
        gross_terminal_bps = 10000 * gross_path.iloc[-1]
        net_terminal_bps = 10000 * (equity.iloc[-1] - 1)
        if name == "frozen_inverse_vol" and abs(net_terminal_bps - _finite(r["ticker_book_net_return_bps"], "published baseline", strictly_positive=False)) > 8:
            raise ValueError("published frozen H20 result differs from source-replayed path")
        daily = equity.pct_change().dropna()
        drawdown = equity / equity.cummax() - 1
        results[name] = {
            "gross_terminal_bps": round(gross_terminal_bps, 4),
            "net_terminal_bps": round(net_terminal_bps, 4),
            "excess_vs_smh_gross_bps": round(net_terminal_bps - smh_gross, 4),
            "excess_vs_smh_after_industry_cost_bps": round(net_terminal_bps - (smh_gross - SMH_COST_BPS), 4),
            "realized_daily_vol_annualized": round(float(daily.std(ddof=1) * math.sqrt(252)), 6),
            "max_close_to_close_drawdown": round(float(drawdown.min()), 6),
            "worst_one_day_return": round(float(daily.min()), 6),
            "concentration_top_five": round(sum(sorted(weights.values(), reverse=True)[:5]), 6),
            "weights_within_cohort": {s: round(weights[s], 10) for s in symbols},
            "evidence_stage": "FROZEN_FORWARD_MEASUREMENT" if name == "frozen_inverse_vol" else "RETROSPECTIVE_ONLY_NO_FORWARD_CREDIT",
        }
    capital = {
        "status": "NOT_MEASURED_NO_UNADJUSTED_ENTRY_CLOSE",
        "broker_quote_proven": False,
        "broker_position_readback_proven": False,
    }
    if raw_close_prices is not None:
        raw = raw_close_prices.copy()
        if not set(symbols).issubset(set(raw.columns)):
            raise ValueError("unadjusted entry close missing symbols")
        raw.index = pd.to_datetime(raw.index).tz_localize(None).normalize()
        raw = raw.sort_index()
        if pd.Timestamp(ENTRY) not in raw.index:
            raise ValueError("unadjusted entry close missing entry date")
        px = {s: _finite(raw.loc[pd.Timestamp(ENTRY), s], f"raw entry close {s}") for s in symbols}
        base_weights = variants["frozen_inverse_vol"]
        min_nav = {s: px[s] / (0.05 * base_weights[s]) for s in symbols}
        scenarios = {}
        for nav in (25_000, 50_000, 100_000, 250_000, 500_000):
            qty = {s: math.floor((0.05 * nav * base_weights[s]) / px[s] + 1e-12) for s in symbols}
            deployed = sum(qty[s] * px[s] for s in symbols)
            scenarios[str(nav)] = {
                "symbols_buyable_at_least_one_share": sum(qty[s] >= 1 for s in symbols),
                "cohort_budget_usd": round(.05 * nav, 2),
                "whole_share_deployed_notional_usd": round(deployed, 2),
                "budget_used_fraction": round(deployed / (.05 * nav), 6),
                "symbol_omissions_due_to_lot_size": [s for s in symbols if qty[s] < 1],
            }
        capital = {
            "status": "HISTORICAL_UNADJUSTED_CLOSE_PROXY_ONLY",
            "reference_close_date": ENTRY,
            "unadjusted_entry_close_usd": {s: round(px[s], 6) for s in symbols},
            "minimum_nav_one_share_each_usd": round(max(min_nav.values()), 2),
            "binding_ticker_at_minimum_nav": max(min_nav, key=min_nav.get),
            "minimum_nav_per_symbol_usd": {s: round(min_nav[s], 2) for s in symbols},
            "whole_share_scenarios": scenarios,
            "no_fractional_shares": True,
            "no_max_shares_or_margin_caps_applied": True,
            "broker_quote_proven": False,
            "broker_position_readback_proven": False,
            "caveat": "Unadjusted historical closing prices, not broker-executable quote; canonical sizing and current-account risk still govern",
        }

    return {
        "schema": SCHEMA,
        "cohort_id": COHORT,
        "source_ref": c["source_ref"],
        "source_adapter_sha256": c["source_adapter_sha256"],
        "source_provider": "yfinance_adjusted_close",
        "signal_date": SIGNAL,
        "entry_date": ENTRY,
        "exit_date": EXIT,
        "observed_session_intervals": len(p) - 1,
        "capital_feasibility": capital,
        "results": results,
        "baseline": "frozen_inverse_vol",
        "policy": {
            "stock_round_trip_cost_bps": STOCK_COST_BPS,
            "smh_round_trip_cost_bps": SMH_COST_BPS,
            "original_cohort_nav_fraction": 0.05,
            "risk_measure": "daily close-to-close, no intraday excursion",
            "alternative_weight_promotion": False,
            "selected_runtime_write": False,
            "broker_action": False,
            "live_execution": False,
        },
        "scientific_disposition": "HISTORICAL_MATCHED_RISK_DIAGNOSTIC_ONLY",
        "limitations": [
            "One correlated completed cohort, not independent forward confirmation",
            "No optimizer, no re-fit, no forecast-magnitude authority",
            "Adjustment/revision risk remains even when adjusted-close history reconciles",
            "Share-rounding, venue liquidity, margin, realized broker commissions not modeled",
        ],
    }


def download_history(symbols):
    import yfinance as yf
    raw = yf.download(sorted(symbols), start="2026-09-11", end="2026-10-15",
                      auto_adjust=False, progress=False, threads=False)
    if raw is None or raw.empty:
        raise ValueError("SOURCE_FAILURE_EMPTY")
    if not isinstance(raw.columns, pd.MultiIndex) or "Adj Close" not in raw.columns.get_level_values(0):
        raise ValueError("adjusted/unadjusted source pairs required")
    return raw["Adj Close"], raw["Close"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--scoreboard", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    lb, sb = a.ledger.read_bytes(), a.scoreboard.read_bytes()
    ledger, scoreboard = json.loads(lb), json.loads(sb)
    c, _, _ = frozen_inputs(ledger, scoreboard)
    adj, raw = download_history(set(c["symbols"]) | {"SMH"})
    evidence = compute(ledger, scoreboard, adj, raw_close_prices=raw)
    evidence["input_sha256"] = {"ledger": hashlib.sha256(lb).hexdigest(), "scoreboard": hashlib.sha256(sb).hexdigest()}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
