from __future__ import annotations

"""Normalize sanitized native forward outputs for the common market scoreboard.

No model source, credentials, broker authority, allocation authority, or private raw data
belongs here. Sensitive model execution remains on the hardened encrypted-compute path;
this module consumes only sanitized native result payloads returned by that path.
"""

import argparse
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

SCHEMA = "foundry.forward_program_adapter.v1"
FROZEN_SYMBOLS = {
    "SEMICONDUCTOR_SHARED_RIDGE": frozenset((
        "AMAT", "APH", "KLAC", "LRCX", "TXN", "NXPI", "ADI",
        "NVDA", "AMD", "MU", "AVGO", "MRVL", "MCHP",
    )),
    "HOMEBUILDERS": frozenset(("CCS", "MHO", "HOV", "BZH")),
    "GENERALIZED_LARGECAP_RIDGE": frozenset(("CAT", "JPM", "UNH", "XOM", "COST", "MSFT")),
}
_NATIVE_BOUNDARY_KEYS = frozenset((
    "runtime_mutation", "broker_authority", "sizing_authority",
    "promotion_authority", "live_trading_authority", "allocation_authority",
    "broker_action", "live_trading_change",
))
_BOOK_KEYS = {
    "ticker_book": frozenset((
        "status", "cohort_target_weights_nav", "cohort_cash_fraction_nav",
        "cohort_gross_exposure", "weighting", "prediction_magnitude_used_for_sizing",
        "realized_vol20_annualized",
    )),
    "industry_book": frozenset((
        "status", "instrument", "mapping", "positive_breadth",
        "cohort_target_weight_nav", "cohort_cash_fraction_nav",
    )),
    "options_book": frozenset(("status", "reason", "trade_authorized", "eligible_underlyings")),
}


def _safe_date(value: object) -> str:
    text = str(value)[:10]
    try:
        if len(text) != 10 or date.fromisoformat(text).isoformat() != text:
            raise ValueError
    except ValueError:
        raise ValueError("public adapter invalid signal date") from None
    return text


def _safe_rows(program: str, rows: list) -> list[dict]:
    allowed = FROZEN_SYMBOLS[program]
    if program == "GENERALIZED_LARGECAP_RIDGE":
        # The frozen snapshot also includes seven semiconductor training-family
        # rows; only its six target-excluded external rows enter public signals.
        allowed = allowed | FROZEN_SYMBOLS["SEMICONDUCTOR_SHARED_RIDGE"]
    if not rows or any(not isinstance(row, dict) or str(row.get("symbol")) not in allowed for row in rows):
        raise ValueError("public adapter symbol outside frozen universe")
    if len({str(row["symbol"]) for row in rows}) != len(rows):
        raise ValueError("public adapter duplicate symbol")
    return rows


def _finite(value: object) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ValueError("public adapter nonfinite numeric field")
    return float(value)


def _safe_book(book: dict) -> dict:
    """Fixed nested public paper-book field projection; no private passthrough."""
    if not isinstance(book, dict) or set(book) != set(_BOOK_KEYS):
        raise ValueError("public adapter book field-set mismatch")
    projected = {}
    for kind, allowed in _BOOK_KEYS.items():
        node = book[kind]
        if not isinstance(node, dict) or set(node) - allowed:
            raise ValueError("public adapter nested book field-set mismatch")
        clean = {}
        for key, value in node.items():
            if key in ("cohort_target_weights_nav", "realized_vol20_annualized"):
                if not isinstance(value, dict) or set(value) - FROZEN_SYMBOLS["SEMICONDUCTOR_SHARED_RIDGE"]:
                    raise ValueError("public adapter book symbol map mismatch")
                clean[key] = {symbol: _finite(amount) for symbol, amount in value.items()}
            elif key == "eligible_underlyings":
                if not isinstance(value, list) or any(str(v) not in FROZEN_SYMBOLS["SEMICONDUCTOR_SHARED_RIDGE"] for v in value):
                    raise ValueError("public adapter book underlyings mismatch")
                clean[key] = list(value)
            elif key in ("prediction_magnitude_used_for_sizing", "trade_authorized"):
                if type(value) is not bool:
                    raise ValueError("public adapter book authority flag mismatch")
                clean[key] = value
            elif key in ("status", "weighting", "instrument", "mapping", "reason"):
                if not isinstance(value, str) or len(value) > 180 or any(ord(c) < 32 for c in value):
                    raise ValueError("public adapter book text field mismatch")
                clean[key] = value
            else:
                clean[key] = _finite(value)
        projected[kind] = clean
    return projected


def _safe_duration_scores(value: object) -> dict:
    if not isinstance(value, dict) or set(value) - {"5", "60"}:
        raise ValueError("public adapter duration score keys mismatch")
    return {key: _finite(amount) for key, amount in value.items()}


def _read(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _date_from_timestamp(value: object) -> str | None:
    return None if value is None else _safe_date(value)


def _prediction_map(rows: list[dict[str, Any]], *keys: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows:
        for key in keys:
            if row.get(key) is not None:
                out[str(row["symbol"])] = float(row[key])
                break
    return out


def _positive(row: dict[str, Any]) -> bool:
    for key in ("positive_value_opportunity", "positive_value_state", "learned_positive"):
        if key in row:
            return bool(row[key])
    for key in ("predicted_fixed20_net_value_bps", "predicted_fixed20_net25_bps"):
        if row.get(key) is not None:
            return float(row[key]) > 0.0
    return False


def _boundaries(native: dict[str, Any]) -> dict[str, Any]:
    raw = native.get("boundaries") or {}
    if not isinstance(raw, dict) or set(raw) - _NATIVE_BOUNDARY_KEYS:
        raise ValueError("public adapter native boundary field-set mismatch")
    if any(type(value) is not bool for value in raw.values()):
        raise ValueError("public adapter native boundary type mismatch")
    return {
        "research_only": True,
        "allocation_authority": False,
        "broker_action": False,
        "runtime_mutation": False,
        "promotion_authority": False,
        "live_trading_change": False,
        "native": {key: raw[key] for key in sorted(raw)},
    }


def adapt_semiconductor(prediction: dict[str, Any], book: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = _safe_rows("SEMICONDUCTOR_SHARED_RIDGE", list(prediction.get("observations") or prediction.get("snapshot") or []))
    signal_date = _safe_date(
        prediction.get("generation_bar_date")
        or prediction.get("bar_date")
        or rows[0].get("bar_date")
    )
    values = _prediction_map(rows, "predicted_fixed20_net_value_bps", "predicted_fixed20_net25_bps")
    positives = [str(r["symbol"]) for r in rows if _positive(r)]
    breadth = len(positives) / len(rows)
    eligible = signal_date >= "2026-09-10"
    if book:
        safe_book = _safe_book(book)
        paper_action: dict[str, Any] = {
            "status": "PAPER_COHORT_READY" if eligible else "PRESTART_NO_BOOK",
            "ticker_book": safe_book["ticker_book"],
            "industry_book": safe_book["industry_book"],
            "options_book": safe_book["options_book"],
        }
    else:
        paper_action = {
            "status": "BOOK_CONSTRUCTOR_INPUT_REQUIRED" if eligible else "PRESTART_NO_BOOK",
            "industry_book_indicative_nav_fraction": 0.05 * breadth if eligible else 0.0,
            "ticker_book": "requires frozen inverse-vol constructor; do not size from forecast magnitude",
            "options_book": "FAIL_CLOSED until native option gates pass",
        }
    return {
        "schema": SCHEMA,
        "program_id": "SEMICONDUCTOR_SHARED_RIDGE",
        "kind": "daily_entry_value_with_three_book_expression",
        "signal_date": signal_date,
        "signal": {
            "predicted_fixed20_net_value_bps": values,
            "positive_symbols": positives,
            "positive_count": len(positives),
            "universe_count": len(rows),
            "positive_breadth": breadth,
        },
        "timing": {
            "decision_cadence": "daily close observation",
            "execution_delay_sessions": 1,
            "holding_horizon_sessions": 20,
            "cohort_nav_fraction": 0.05,
            "max_concurrent_cohorts": 20,
            "entry_rule": "signal at close D; execute cohort on next common market session D+1",
            "exit_rule": "expire cohort exactly 20 common sessions after execution",
        },
        "paper_action": paper_action,
        "benchmarks": ["cash", "SMH", "QQQ", "equal_weight_13_name_semiconductor_universe"],
        "validation": {
            "prospective_start_signal_date": "2026-09-10",
            "scientific_forward_credit": eligible,
            "state": "PROSPECTIVE_ELIGIBLE" if eligible else "DESCRIPTIVE_PRESTART",
        },
        "decision_use": (
            "Use as semiconductor entry/timing evidence. Positive forecasts authorize only the frozen paper cohort rules; "
            "prediction magnitude is not ranking or sizing authority. Prefer sector-level corroboration unless prospective "
            "stock-selection excess versus SMH is established."
        ),
        "boundaries": _boundaries(prediction),
    }


def adapt_homebuilders(native: dict[str, Any]) -> dict[str, Any]:
    if native.get("schema") != "foundry.research.homebuilders_adaptive_duration_forward.v1":
        raise ValueError("unexpected Homebuilders adaptive-duration schema")
    rows = _safe_rows("HOMEBUILDERS", list(native.get("observations") or []))
    signal_date = _date_from_timestamp((native.get("duration_snapshot") or {}).get("timestamp"))
    admitted = [
        str(r["symbol"])
        for r in rows
        if bool(r.get("duration_applicable_to_parent_admitted_opportunity"))
    ]
    horizons = {
        str(r["symbol"]): int(r["frozen_duration_horizon_sessions"])
        for r in rows
        if r.get("frozen_duration_horizon_sessions") is not None
    }
    predictions = _prediction_map(rows, "predicted_fixed20_net25_bps", "predicted_fixed20_net_value_bps")
    duration_scores = {
        str(r["symbol"]): _safe_duration_scores(r.get("predicted_after25_bps_per_session", {}))
        for r in rows
    }
    historical = native.get("historical_evidence") or {}
    return {
        "schema": SCHEMA,
        "program_id": "HOMEBUILDERS",
        "kind": "entry_admission_plus_adaptive_duration",
        "signal_date": signal_date,
        "signal": {
            "predicted_fixed20_net25_bps": predictions,
            "admitted_symbols": admitted,
            "duration_horizon_sessions_by_symbol": horizons,
            "predicted_after25_bps_per_session": duration_scores,
        },
        "timing": {
            "decision_cadence": "daily observer when fresh close exists",
            "execution_delay_sessions": 1,
            "candidate_holding_horizons_sessions": [5, 60],
            "entry_rule": "parent fixed20 admission is frozen on close D; outcome accounting begins from next-session D+1 entry",
            "exit_rule": "resolve each admitted observation after its frozen 5- or 60-session horizon",
        },
        "paper_action": {
            "status": "OBSERVATION_ONLY_NO_FROZEN_SIZING_AUTHORITY",
            "admitted_symbols": admitted,
            "holding_horizon_sessions_by_symbol": {s: horizons[s] for s in admitted if s in horizons},
            "instruction": "Do not invent weights. Use admission + duration as sector/ticker decision evidence until a prospective sizing contract is frozen.",
        },
        "benchmarks": ["ITB", "QQQ"],
        "validation": {
            "historical_gate_pass": bool(historical.get("historical_gate_pass", False)),
            "historical_fixed20_matched_itb_excess_bps": historical.get("homebuilders_fixed20_matched_itb_excess_bps"),
            "historical_adaptive_matched_itb_excess_bps": historical.get("homebuilders_binary_5_60_matched_itb_excess_bps"),
            "state": "PROSPECTIVE_DIAGNOSTIC_NO_PROMOTION",
        },
        "decision_use": (
            "Use admitted names as Homebuilder opportunity evidence and the frozen 5/60 selector as holding-window evidence. "
            "The duration child cannot admit, veto, size, or trade; portfolio sizing remains intentionally unassigned."
        ),
        "boundaries": _boundaries(native),
    }


def adapt_largecap(native: dict[str, Any]) -> dict[str, Any]:
    rows = _safe_rows("GENERALIZED_LARGECAP_RIDGE", list(native.get("snapshot") or native.get("observations") or []))
    signal_date = _safe_date(native.get("bar_date") or native.get("generation_bar_date") or rows[0].get("bar_date"))
    external = [r for r in rows if str(r.get("role", "")).startswith("external")] or rows
    if any(str(r["symbol"]) not in FROZEN_SYMBOLS["GENERALIZED_LARGECAP_RIDGE"] for r in external):
        raise ValueError("public adapter external symbol outside frozen universe")
    values = _prediction_map(external, "predicted_fixed20_net_value_bps", "predicted_fixed20_net25_bps")
    positives = [str(r["symbol"]) for r in external if _positive(r)]
    negatives = [str(r["symbol"]) for r in external if not _positive(r)]
    return {
        "schema": SCHEMA,
        "program_id": "GENERALIZED_LARGECAP_RIDGE",
        "kind": "target_excluded_transport_corroboration",
        "signal_date": signal_date,
        "signal": {
            "predicted_fixed20_net_value_bps": values,
            "positive_symbols": positives,
            "negative_symbols": negatives,
        },
        "timing": {
            "decision_cadence": "daily close observation",
            "execution_delay_sessions": 1,
            "holding_horizon_sessions": 20,
            "entry_rule": "signal at close D corresponds to next-session D+1 fixed20 observation window",
            "exit_rule": "resolve after 20 sessions from D+1 entry",
        },
        "paper_action": {
            "status": "CORROBORATION_ONLY_NO_FROZEN_BOOK",
            "watch_positive": positives,
            "avoid_or_falsify": negatives,
            "instruction": "Do not allocate from this transport alone; require independent evidence or a prospectively frozen book rule.",
        },
        "benchmarks": ["SPY", "QQQ", "appropriate_sector_or_industry_benchmark"],
        "validation": {
            "external_target_history_used_in_training": False,
            "state": "TRANSPORT_FORWARD_OBSERVATION",
        },
        "decision_use": (
            "Use as cross-sector corroboration/discovery. It is the semiconductor-trained Ridge transported to target-excluded "
            "large caps, not an independently trained stock-selection model."
        ),
        "boundaries": _boundaries(native),
    }


def adapt(program: str, native: dict[str, Any], book: dict[str, Any] | None = None) -> dict[str, Any]:
    key = program.upper().replace("-", "_")
    if key in {"SEMICONDUCTOR", "SEMICONDUCTOR_SHARED_RIDGE"}:
        return adapt_semiconductor(native, book)
    if key in {"HOMEBUILDERS", "HOMEBUILDER"}:
        return adapt_homebuilders(native)
    if key in {"GENERALIZED_LARGECAP_RIDGE", "LARGECAP", "GENERALIZED_LARGECAP"}:
        return adapt_largecap(native)
    raise ValueError(f"unsupported program {program}")


def self_test() -> None:
    semi = adapt_semiconductor({
        "generation_bar_date": "2026-09-10",
        "observations": [
            {"symbol": "AMAT", "predicted_fixed20_net_value_bps": 500.0, "positive_value_opportunity": True},
            {"symbol": "NVDA", "predicted_fixed20_net_value_bps": -10.0, "positive_value_opportunity": False},
        ],
    })
    assert semi["timing"]["execution_delay_sessions"] == 1
    assert semi["timing"]["holding_horizon_sessions"] == 20
    assert semi["paper_action"]["industry_book_indicative_nav_fraction"] == 0.025
    hb = adapt_homebuilders({
        "schema": "foundry.research.homebuilders_adaptive_duration_forward.v1",
        "duration_snapshot": {"timestamp": "2026-09-10T00:00:00+00:00"},
        "historical_evidence": {"historical_gate_pass": False, "homebuilders_binary_5_60_matched_itb_excess_bps": 18.3},
        "observations": [
            {"symbol": "CCS", "predicted_fixed20_net25_bps": 100.0, "duration_applicable_to_parent_admitted_opportunity": True, "frozen_duration_horizon_sessions": 5, "predicted_after25_bps_per_session": {"5": 3.0, "60": 1.0}},
        ],
    })
    assert hb["signal"]["admitted_symbols"] == ["CCS"]
    assert hb["timing"]["candidate_holding_horizons_sessions"] == [5, 60]
    large = adapt_largecap({
        "bar_date": "2026-09-10",
        "snapshot": [
            {"symbol": "CAT", "role": "external_target_excluded", "predicted_fixed20_net_value_bps": 300.0, "positive_value_state": True},
            {"symbol": "MSFT", "role": "external_target_excluded", "predicted_fixed20_net_value_bps": -50.0, "positive_value_state": False},
        ],
    })
    assert large["signal"]["positive_symbols"] == ["CAT"]
    assert large["paper_action"]["status"] == "CORROBORATION_ONLY_NO_FROZEN_BOOK"
    # Synthetic nested sentinel rejection: never pass native boundaries or
    # three-book extras into a public sanitized adapter.
    for mutated in (
        {"generation_bar_date": "2026-09-10", "observations": [
            {"symbol": "AMAT", "predicted_fixed20_net_value_bps": 10.0}],
         "boundaries": {"PRIVATE_SENTINEL": {"secret": "never_public"}}},
        {"generation_bar_date": "2026-09-10", "observations": [
            {"symbol": "PRIVATE_SENTINEL", "predicted_fixed20_net_value_bps": 10.0}]},
    ):
        try:
            adapt_semiconductor(mutated)
        except ValueError as exc:
            assert "SENTINEL" not in str(exc)
        else:
            raise AssertionError("private native field reached public adapter")
    try:
        adapt_semiconductor({
            "generation_bar_date": "2026-09-10",
            "observations": [{"symbol": "AMAT", "predicted_fixed20_net_value_bps": 10.0}],
        }, book={
            "ticker_book": {"status": "PAPER_COHORT_READY", "PRIVATE_SENTINEL": {"secret": "never_public"}},
            "industry_book": {"status": "PAPER_COHORT_READY"},
            "options_book": {"status": "FAIL_CLOSED"},
        })
    except ValueError as exc:
        assert "SENTINEL" not in str(exc)
    else:
        raise AssertionError("private nested book field reached public adapter")
    print("FORWARD_NATIVE_PUBLIC_ADAPTER_NESTED_SENTINEL_SELF_TEST=PASS")
    print("FORWARD_NATIVE_PROGRAM_ADAPTER_SELF_TEST=PASS")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--program")
    ap.add_argument("--input")
    ap.add_argument("--book")
    ap.add_argument("--output")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.program or not args.input or not args.output:
        ap.error("--program, --input and --output are required unless --self-test")
    out = adapt(args.program, _read(args.input) or {}, _read(args.book))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"program_id": out["program_id"], "signal_date": out.get("signal_date"), "paper_action_status": (out.get("paper_action") or {}).get("status")}, sort_keys=True))


if __name__ == "__main__":
    main()
