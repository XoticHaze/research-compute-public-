from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

SCHEMA = "research.p160_forward_observer_r1"
PROGRAM_ID = "P160_FIXED_P46_P47_COMBINATION"
FROZEN_SOURCE_REF = "c575e02aba939b283c0aa409d9bc21f000c0762c"
FROZEN_SOURCE_BLOB_SHA = "89d8e4c004536310e588623203e8e23e8aac15d9"
FIRST_ELIGIBLE_BOUNDARY = date(2026, 9, 30)
PRIMARY_COST_BPS = 50.0
P46_UNIVERSE = ("SPY", "QQQ", "TLT", "GLD", "DBC")
P47_UNIVERSE = ("SMH", "XBI", "ITB", "KRE", "ITA", "IGV", "IWM", "XRT")
UNIVERSE = tuple(dict.fromkeys(P46_UNIVERSE + P47_UNIVERSE))


def _last_complete_month_end(asof: date) -> pd.Timestamp:
    return pd.Timestamp(asof).to_period("M").start_time - pd.Timedelta(days=1)


def _download_panel(asof: date) -> tuple[pd.DataFrame, pd.Timestamp, str]:
    cut = _last_complete_month_end(asof)
    raw = yf.download(
        list(UNIVERSE),
        start="2005-01-01",
        end=(pd.Timestamp(asof) + pd.Timedelta(days=1)).date().isoformat(),
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if raw.empty:
        raise RuntimeError("P160 observer received no market data")
    close = raw["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame()
    if isinstance(close.columns, pd.MultiIndex):
        close.columns = close.columns.get_level_values(-1)
    missing = sorted(set(UNIVERSE) - set(map(str, close.columns)))
    if missing:
        raise RuntimeError(f"P160 observer missing symbols: {missing}")
    panel = close.loc[:, list(UNIVERSE)].astype(float).dropna(how="all")
    idx = pd.to_datetime(panel.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert(None)
    panel.index = pd.DatetimeIndex(idx).normalize()
    panel = panel.loc[panel.index <= cut]
    if panel.empty or panel.index.max().to_period("M") != cut.to_period("M"):
        raise RuntimeError(f"complete month data unavailable for {cut.date()}")
    digest = hashlib.sha256(
        panel.reset_index().to_csv(index=False, float_format="%.10g").encode("utf-8")
    ).hexdigest()
    return panel, cut, digest


def _rank_snapshot(daily: pd.DataFrame, symbols: tuple[str, ...], cut: pd.Timestamp) -> dict[str, Any]:
    monthly = daily.resample("ME").last()
    vol = (
        daily.pct_change(fill_method=None)
        .rolling(126, min_periods=100)
        .std(ddof=0)
        .mul(252 ** 0.5)
        .resample("ME")
        .last()
    )
    trend = (daily / daily.rolling(200, min_periods=160).mean() - 1).resample("ME").last()
    drawdown = (daily / daily.rolling(126, min_periods=100).max() - 1).resample("ME").last()
    momentum = monthly.pct_change(6)
    month_key = cut.to_period("M").to_timestamp("M")
    if month_key not in monthly.index:
        raise RuntimeError(f"month-end snapshot unavailable for {cut.date()}")
    z = pd.DataFrame(
        {
            "momentum_6m": momentum.loc[month_key, list(symbols)],
            "trend_200d": trend.loc[month_key, list(symbols)],
            "inverse_vol_126d": -vol.loc[month_key, list(symbols)],
            "drawdown_126d": drawdown.loc[month_key, list(symbols)],
        },
        index=list(symbols),
    )
    if z.isna().any().any():
        bad = z[z.isna().any(axis=1)].index.tolist()
        raise RuntimeError(f"incomplete frozen P160 factors at {cut.date()}: {bad}")
    pct = z.rank(axis=0, pct=True, method="average")
    composite = pct.mean(axis=1)
    ordered = sorted(symbols, key=lambda symbol: (-float(composite[symbol]), symbol))
    return {
        "ordered": ordered,
        "composite_score": {s: round(float(composite[s]), 10) for s in symbols},
        "factor_percentiles": {
            s: {k: round(float(v), 10) for k, v in pct.loc[s].to_dict().items()} for s in symbols
        },
    }


def _target_weights(p46_selected: list[str], p47_selected: list[str]) -> dict[str, float]:
    if len(p46_selected) != 2 or len(p47_selected) != 3:
        raise RuntimeError("P160 frozen cardinality violated")
    out: dict[str, float] = {}
    for symbol in p46_selected:
        out[symbol] = out.get(symbol, 0.0) + 0.25
    for symbol in p47_selected:
        out[symbol] = out.get(symbol, 0.0) + (1.0 / 6.0)
    if abs(sum(out.values()) - 1.0) > 1e-10:
        raise RuntimeError("P160 target weights do not sum to 1")
    return dict(sorted(out.items()))


def _matched_weights() -> dict[str, float]:
    out = {s: 0.5 / len(P46_UNIVERSE) for s in P46_UNIVERSE}
    out.update({s: 0.5 / len(P47_UNIVERSE) for s in P47_UNIVERSE})
    return dict(sorted(out.items()))


def build(asof: date) -> dict[str, Any]:
    panel, cut, panel_sha = _download_panel(asof)
    p46 = _rank_snapshot(panel, P46_UNIVERSE, cut)
    p47 = _rank_snapshot(panel, P47_UNIVERSE, cut)
    p46_selected = list(p46["ordered"][:2])
    p47_selected = list(p47["ordered"][:3])
    weights = _target_weights(p46_selected, p47_selected)
    prospective = cut.date() >= FIRST_ELIGIBLE_BOUNDARY
    state = "PROSPECTIVE_ELIGIBLE" if prospective else "PRESTART_DESCRIPTIVE_SHADOW"
    holding_month = (cut + pd.offsets.MonthBegin(1)).strftime("%Y-%m")
    return {
        "schema": SCHEMA,
        "program_id": PROGRAM_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_data_asof": asof.isoformat(),
        "signal_month_end": cut.date().isoformat(),
        "holding_month": holding_month,
        "state": state,
        "scientific_forward_credit": prospective,
        "frozen_identity": {
            "source_ref": FROZEN_SOURCE_REF,
            "source_blob_sha": FROZEN_SOURCE_BLOB_SHA,
            "construction": "fixed_50_50_p46_top2_p47_top3",
            "primary_cost_bps": PRIMARY_COST_BPS,
            "no_weight_search": True,
        },
        "signal": {
            "p46_cross_asset_top2": p46_selected,
            "p47_industry_top3": p47_selected,
            "p46_scores": p46["composite_score"],
            "p47_scores": p47["composite_score"],
            "p46_factor_percentiles": p46["factor_percentiles"],
            "p47_factor_percentiles": p47["factor_percentiles"],
        },
        "paper_action": {
            "status": "PROSPECTIVE_COHORT_READY" if prospective else "DESCRIPTIVE_SHADOW_ONLY",
            "target_weights": weights,
            "matched_control_weights": _matched_weights(),
            "portfolio_authority": False,
        },
        "timing": {
            "decision_cadence": "monthly",
            "signal_rule": "rank from the last complete month-end close",
            "execution_rule": "execute only on the next common market session after the signal close",
            "execution_delay_sessions": 1,
            "holding_rule": "hold until the next monthly decision boundary, then execute the next target on the following common session",
            "first_scientific_signal_boundary": FIRST_ELIGIBLE_BOUNDARY.isoformat(),
            "same_close_execution_prohibited": True,
        },
        "benchmarks": {
            "matched": "50/50 same-universe equal-weight controls",
            "opportunity": ["SPY", "QQQ"],
            "primary_cost_bps": PRIMARY_COST_BPS,
        },
        "source": {
            "provider": "Yahoo Finance via yfinance; research-only public data",
            "panel_sha256": panel_sha,
            "universe": list(UNIVERSE),
        },
        "decision_use": (
            "Independent-validation challenger for the frozen P160 combination. P47 remains parked as a standalone sleeve; "
            "this observer does not reactivate it or grant allocation authority."
        ),
        "boundaries": {
            "research_only": True,
            "descriptive_prestart_not_forward_credit": True,
            "p47_standalone_reactivated": False,
            "allocation_authority": False,
            "promotion_authority": False,
            "runtime_authority": False,
            "broker_action": False,
            "live_trading_change": False,
            "parameter_rescue": False,
        },
    }


def self_test() -> None:
    weights = _target_weights(["SPY", "QQQ"], ["SMH", "ITB", "XBI"])
    assert weights == {
        "ITB": 1 / 6,
        "QQQ": 0.25,
        "SMH": 1 / 6,
        "SPY": 0.25,
        "XBI": 1 / 6,
    }
    matched = _matched_weights()
    assert abs(sum(matched.values()) - 1.0) < 1e-10
    assert _last_complete_month_end(date(2026, 9, 13)).date() == date(2026, 8, 31)
    assert _last_complete_month_end(date(2026, 10, 1)).date() == date(2026, 9, 30)
    assert FIRST_ELIGIBLE_BOUNDARY == date(2026, 9, 30)
    print("P160_FORWARD_OBSERVER_SELF_TEST=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asof")
    parser.add_argument("--output", default="artifacts/p160_forward_observation_r1.json")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    asof = date.fromisoformat(args.asof) if args.asof else datetime.now(timezone.utc).date()
    result = build(asof)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({
        "state": result["state"],
        "signal_month_end": result["signal_month_end"],
        "holding_month": result["holding_month"],
        "p46": result["signal"]["p46_cross_asset_top2"],
        "p47": result["signal"]["p47_industry_top3"],
        "weights": result["paper_action"]["target_weights"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
