from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Use the already-merged standalone economic CURRENT admission, never a parallel source gate.
if __package__:
    from .forward_p249_p266_shadow_r1 import current_publication_admitted
    from .forward_prospective_cohort_ledger_r1 import (
        CONTRACTS, _reject_adapter_duplicate_keys, _reject_adapter_nonfinite_constant,
    )
else:
    from forward_p249_p266_shadow_r1 import current_publication_admitted
    from forward_prospective_cohort_ledger_r1 import (
        CONTRACTS, _reject_adapter_duplicate_keys, _reject_adapter_nonfinite_constant,
    )

SCHEMA = "research.forward_market_scoreboard_r1"
ADAPTER_SCHEMA = "foundry.forward_program_adapter.v1"
LEDGER_SCHEMA = "research.forward_prospective_cohort_ledger_r1"
EXPECTED_PRIVATE_ADAPTERS = (
    "SEMICONDUCTOR_SHARED_RIDGE",
    "HOMEBUILDERS",
    "GENERALIZED_LARGECAP_RIDGE",
)


def _load(root: Path, name: str) -> dict[str, Any] | None:
    """Reject conflicting transport copies of a canonical scoreboard input.

    A recursive artifact root can contain multiple copies of the same producer
    basename. Never select one by directory enumeration order. Byte-identical
    copies are safe; a conflicting copy fails closed without exposing paths or
    input contents in public logs.
    """
    matches = sorted(root.rglob(name))
    if not matches:
        return None
    raw = matches[0].read_bytes()
    digest = hashlib.sha256(raw).digest()
    for path in matches[1:]:
        if hashlib.sha256(path.read_bytes()).digest() != digest:
            raise ValueError(f"CONFLICTING_SCOREBOARD_INPUT:{name}")
    # Every explicitly named canonical producer can affect forward score/health.
    # Last-wins duplicate keys or NaN must not silently change P249/P46/P558/
    # CLO freshness, matched economics or prospective ledger identities.
    # Reuse the existing strict prospective JSON parser, not a second gate.
    payload = json.loads(
        raw, object_pairs_hook=_reject_adapter_duplicate_keys,
        parse_constant=_reject_adapter_nonfinite_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"INVALID_SCOREBOARD_INPUT:{name}")
    return payload


def _load_native_adapters(root: Path) -> dict[str, dict[str, Any]]:
    """Never select a native program by filesystem enumeration order.

    Identical byte-for-byte transport copies are harmless. Conflicting
    first-seen program identities must fail before scoreboard construction.
    """
    out: dict[str, dict[str, Any]] = {}
    seen_sha256: dict[str, str] = {}
    for path in root.rglob("*.json"):
        try:
            raw = path.read_bytes()
            # Preserve top-level schema pairs during discovery. A recognized
            # adapter must not evade strict validation by repeating "schema"
            # with a later unrelated value (default json.loads is last-wins).
            # Unrelated artifacts, including nested lookalikes, remain ignored.
            top_pairs = json.loads(raw, object_pairs_hook=lambda pairs: pairs)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(top_pairs, list) or not any(
            isinstance(pair, tuple) and pair[0] == "schema" and pair[1] == ADAPTER_SCHEMA
            for pair in top_pairs
        ):
            continue
        # Reuse the canonical prospective ledger's strict native-adapter parser.
        # A nested duplicate key or NaN can otherwise change model/source
        # identity in the scoreboard while the ledger rejects the same bytes.
        # Only recognized native adapters are strict-parsed: unrelated JSON
        # artifacts must not become accidental scoreboard source blockers.
        payload = json.loads(
            raw, object_pairs_hook=_reject_adapter_duplicate_keys,
            parse_constant=_reject_adapter_nonfinite_constant,
        )
        program_id = str(payload.get("program_id") or "")
        if program_id not in EXPECTED_PRIVATE_ADAPTERS:
            continue
        digest = hashlib.sha256(raw).hexdigest()
        if program_id in seen_sha256:
            if seen_sha256[program_id] != digest:
                # Do not echo source paths, raw payloads or private identifiers.
                raise ValueError(f"DUPLICATE_NATIVE_ADAPTER_PROGRAM_ID:{program_id}")
            continue
        seen_sha256[program_id] = digest
        out[program_id] = payload
    return out


def _bp(x: float | int | None) -> float | None:
    return None if x is None else round(float(x) * 10000.0, 2)


def _funded_excess_metrics(core_cumulative: Any, combo_cumulative: Any) -> tuple[float | None, float | None]:
    """Relative wealth of existing constant-target shadow NAVs, not a monthly-drift funded execution."""
    try:
        core, combo = float(core_cumulative), float(combo_cumulative)
    except (TypeError, ValueError):
        return None, None
    if not (math.isfinite(core) and math.isfinite(combo)) or core <= -1.0 or combo <= -1.0:
        return None, None
    return (1.0 + combo) / (1.0 + core) - 1.0, combo - core


def _positive_session_stats(values: list[float]) -> dict[str, Any]:
    observed = len(values)
    positive = sum(1 for value in values if float(value) > 0.0)
    return {
        "observed_sessions": observed,
        "positive_sessions": positive,
        "hit_rate": None if observed == 0 else round(positive / observed, 6),
    }


def _challenger_session_stats(fwd: dict[str, Any]) -> dict[str, Any]:
    """Only report forward hit rates when the entire matched date book exists."""
    empty = _positive_session_stats([])
    invalid = {
        "complete": False,
        "vs_incumbent": empty,
        "vs_matched_cash_control": empty,
    }
    metrics = fwd.get("challenger_if_flattened_now") or {}
    days = metrics.get("days")
    challenger_rows = fwd.get("challenger_observations")
    matched_rows = fwd.get("matched_control_observations")
    if (
        isinstance(days, bool) or not isinstance(days, int) or days < 0
        or not isinstance(challenger_rows, list)
        or not isinstance(matched_rows, list)
        or len(challenger_rows) != days or len(matched_rows) != days
    ):
        return invalid

    def indexed(rows: list[dict[str, Any]], required: tuple[str, ...]) -> dict[str, dict[str, Any]] | None:
        by_day: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                return None
            day = row.get("date")
            if not isinstance(day, str) or not day or day in by_day:
                return None
            if any(
                isinstance(row.get(key), bool)
                or not isinstance(row.get(key), (int, float))
                or not math.isfinite(row[key])
                for key in required
            ):
                return None
            by_day[day] = row
        return by_day

    challenger = indexed(challenger_rows, ("net_return", "core_return"))
    matched = indexed(matched_rows, ("net_return",))
    if challenger is None or matched is None or challenger.keys() != matched.keys():
        return invalid
    incumbent_excess = [
        row["net_return"] - row["core_return"] for row in challenger.values()
    ]
    matched_excess = [
        row["net_return"] - matched[day]["net_return"]
        for day, row in challenger.items()
    ]
    # Individually finite returns can still overflow on subtraction.
    # Never publish a complete matched book with nonfinite derived excess.
    if not all(math.isfinite(value) for value in incumbent_excess + matched_excess):
        return invalid
    return {
        "complete": True,
        "vs_incumbent": _positive_session_stats(incumbent_excess),
        "vs_matched_cash_control": _positive_session_stats(matched_excess),
    }


def _grade(days: int, scientific_credit: bool = True) -> str:
    if not scientific_credit:
        return "SHAKEDOWN_ONLY"
    if days <= 0:
        return "NO_FORWARD_SAMPLE"
    if days < 5:
        return "INSUFFICIENT_SAMPLE"
    if days < 20:
        return "EVIDENCE_ACCUMULATING"
    return "REPORTABLE_FORWARD_SAMPLE"


def _weights_text(weights: dict[str, Any], limit: int = 6) -> str:
    ranked = sorted(((k, float(v)) for k, v in weights.items() if float(v) > 0), key=lambda kv: kv[1], reverse=True)
    return ", ".join(f"{k} {v:.1%}" for k, v in ranked[:limit]) or "none"


def _p46(x: dict[str, Any] | None) -> dict[str, Any]:
    if not x:
        return {"program_id": "P46", "status": "MISSING", "decision_use": "unavailable"}
    d = x.get("decision", {})
    shadow = x.get("operational_shadow", {})
    # A nonempty string such as "false" must never grant forward credit.
    # Only the producer's literal JSON boolean true may enable the projection.
    credit = d.get("scientific_forward_credit_authorized") is True
    selected = list(d.get("selected", []))
    weights = d.get("target_weights", {})
    return {
        "program_id": "P46",
        "kind": "cross_asset_selector",
        "signal": {
            "scores": d.get("scores", {}),
            "selected": selected,
            "holding_month": d.get("holding_month"),
        },
        "timing": {
            "decision_cadence": "monthly",
            "entry_rule": "rebalance only at the frozen monthly decision/admission boundary; a daily rerun is not a new trade",
            "holding_rule": "hold target weights for the frozen holding month until the next valid monthly rebalance",
        },
        "paper_action": weights,
        "action_text": f"Hold {_weights_text(weights)} for the frozen holding month.",
        "scientific_forward_credit": credit,
        "forward_days": 0 if shadow.get("anchor_date") == shadow.get("latest_date") else None,
        "validation_grade": _grade(0, credit),
        "decision_use": (
            "Cross-asset regime/context signal only until prospective credit is active. "
            "Selection indicates relative preference, not a return forecast."
        ),
        "boundaries": x.get("boundaries", {}),
    }


def _p249(x: dict[str, Any] | None) -> dict[str, Any]:
    if not x:
        return {"program_id": "P249_P266", "status": "MISSING", "decision_use": "unavailable"}
    admitted = current_publication_admitted(x)
    health = x.get("source_health") if isinstance(x.get("source_health"), dict) else {}
    blocked_grade = ("SOURCE_GAP_UNRESOLVED" if x.get("status") == "SOURCE_GAP_UNRESOLVED" or health.get("unresolved_forward_gap") is not None else "ECONOMIC_SOURCE_NOT_ADMITTED")
    fwd = x.get("forward", {})
    core = fwd.get("p249_core_net", {})
    combo = fwd.get("p249_plus_p266_net", {})
    days = int(combo.get("days", 0) or 0)
    state = x.get("current_state", {})
    increment_stats = _positive_session_stats([
        float(row.get("satellite_increment_net", 0.0))
        for row in (fwd.get("observations") or [])
        if row.get("satellite_increment_net") is not None
    ])
    funded_relative_wealth, funded_return_difference = _funded_excess_metrics(
        core.get("cumulative_return"), combo.get("cumulative_return")
    )
    def economic(value: Any) -> Any:
        return value if admitted else None

    return {
        "program_id": "P249_P266",
        "kind": "portfolio_construction_plus_industry_momentum_satellite",
        "signal": {
            "p249_core_weights": state.get("p249_core", {}),
            "p266_industry_weights": state.get("p266", {}),
        },
        "timing": {
            "decision_cadence": "frozen monthly portfolio decision",
            "entry_rule": "frozen monthly target selection only; observer rows are not trade or funded rebalance evidence",
            "holding_rule": "monthly target identity is frozen, but the current constant-target shadow reapplies target weights daily without intramonth turnover costs; not a drift-aware funded monthly hold",
        },
        "paper_action": state.get("p249_plus_p266", {}),
        "paper_action_authority": "frozen_monthly_context" if admitted else "prior_frozen_context_only_not_new_economic_current",
        "action_text": (f"Frozen combined portfolio: {_weights_text(state.get('p249_plus_p266', {}), 10)}." if admitted else "Economic CURRENT held: source gap/unadmitted; frozen weights are prior context, not a new rebalance."),
        "forward_days": days if admitted else None,
        "economic_current_admitted": admitted,
        "source_status": x.get("status"),
        "scorecard": {
            "p249_core_net_cumulative_bps": economic(_bp(core.get("cumulative_return"))),
            "p249_plus_p266_net_cumulative_bps": economic(_bp(combo.get("cumulative_return"))),
            "p266_increment_cumulative_bps": economic(_bp(funded_relative_wealth)),
            "p266_relative_wealth_excess_bps": economic(_bp(funded_relative_wealth)),
            "p266_cumulative_return_difference_bps": economic(_bp(funded_return_difference)),
            "p266_legacy_compounded_daily_spread_bps": economic(_bp(fwd.get("satellite_increment_cumulative"))),
            "p266_increment_metric_semantics": economic("CONSTANT_TARGET_SHADOW_COMBO_NAV_OVER_CORE_NAV_MINUS_ONE"),
            "p266_execution_limit": economic("IMPLICIT_DAILY_TARGET_RESET_WITH_UNPRICED_INTRAMONTH_TURNOVER"),
            "p266_increment_observed_sessions": economic(increment_stats["observed_sessions"]),
            "p266_increment_positive_sessions": economic(increment_stats["positive_sessions"]),
            "p266_increment_session_hit_rate": economic(increment_stats["hit_rate"]),
            "p249_core_annualized_vol": economic(core.get("annualized_vol")),
            "p249_plus_p266_annualized_vol": economic(combo.get("annualized_vol")),
        },
        "validation_grade": _grade(days) if admitted else blocked_grade,
        "source_health": x.get("source_health", {}),
        "decision_use": (
            "This is not a price target. Weights are the frozen portfolio expression. "
            "Use prospective return, drawdown and the P266 incremental result to decide whether the construction adds value."
        ),
        "boundaries": x.get("boundaries", {}),
    }


def _challenger(x: dict[str, Any] | None, program_id: str, alt: str) -> dict[str, Any]:
    if not x:
        return {"program_id": program_id, "status": "MISSING", "decision_use": "unavailable"}
    fwd = x.get("forward", {})
    metrics = fwd.get("challenger_if_flattened_now", {})
    days = int(metrics.get("days", 0) or 0)
    pos = x.get("current_positions", {}).get("challenger", {})
    session_stats = _challenger_session_stats(fwd)
    matched_complete = session_stats["complete"]
    basis = fwd.get("comparison_cost_basis") or {}
    challenger_nav = metrics.get("cumulative_return")
    incumbent_nav = (fwd.get("incumbent") or {}).get("cumulative_return")
    matched_nav = (fwd.get("matched_control_if_flattened_now") or {}).get("cumulative_return")

    def admitted_nav(value: Any) -> bool:
        # A cost-basis declaration cannot authenticate missing, string, bool,
        # nonfinite or bankrupt funded NAVs. Catch oversized JSON integers
        # before float conversion; guard bps multiplication too.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        try:
            numeric = float(value)
        except (OverflowError, ValueError):
            return False
        return (
            math.isfinite(numeric) and numeric > -1.0
            and math.isfinite(numeric * 10000.0)
        )

    def replayed_nav(rows: list[dict[str, Any]], key: str, exit_fee: float) -> float | None:
        # The producer publishes daily net returns BEFORE its final 25bp
        # flattening fee. Recompute all three books rather than trusting a
        # declared cost basis plus unrelated finite terminal NAVs.
        if not rows:
            return None
        wealth = 1.0
        for index, row in enumerate(rows):
            try:
                daily = float(row[key]) - (exit_fee if index == len(rows) - 1 else 0.0)
                wealth *= 1.0 + daily
            except (KeyError, TypeError, ValueError, OverflowError):
                return None
            if not math.isfinite(wealth) or wealth <= 0.0:
                return None
        return wealth - 1.0

    nav_reconciled = False
    if (
        matched_complete and days > 0
        and x.get("contract", {}).get("entry_and_mark_to_market_exit_cost_bps_each") == 25
        and all(admitted_nav(nav) for nav in (challenger_nav, incumbent_nav, matched_nav))
    ):
        challenger_rows = fwd["challenger_observations"]
        matched_rows = fwd["matched_control_observations"]
        expected = (
            replayed_nav(challenger_rows, "net_return", 0.0025),
            replayed_nav(challenger_rows, "core_return", 0.0),
            replayed_nav(matched_rows, "net_return", 0.0025),
        )
        nav_reconciled = all(
            value is not None and math.isfinite(value)
            and math.isclose(value, published, rel_tol=1e-10, abs_tol=1e-10)
            for value, published in zip(expected, (challenger_nav, incumbent_nav, matched_nav))
        )

    both_net = (
        matched_complete
        and days > 0
        and nav_reconciled
        and basis.get("challenger_minus_incumbent_cumulative")
            == "CHALLENGER_NET_IF_FLATTENED_NOW_MINUS_UNCHANGED_INCUMBENT_NET"
        and basis.get("challenger_minus_matched_cumulative")
            == "BOTH_NET_IF_FLATTENED_NOW"
        and basis.get("legacy_pre_exit_spreads_not_used") is True
    )
    incumbent_relative, _ = (
        _funded_excess_metrics(incumbent_nav, challenger_nav)
        if both_net else (None, None)
    )
    matched_relative, _ = (
        _funded_excess_metrics(matched_nav, challenger_nav)
        if both_net else (None, None)
    )
    # A near-zero control wealth can overflow a finite NAV ratio. Such a
    # ratio is not a valid both-net scorecard, even if all inputs were finite.
    both_net = (
        both_net and incumbent_relative is not None and matched_relative is not None
        and math.isfinite(incumbent_relative) and math.isfinite(matched_relative)
        and math.isfinite(incumbent_relative * 10000.0)
        and math.isfinite(matched_relative * 10000.0)
    )
    if not both_net:
        incumbent_relative = matched_relative = None
    return {
        "program_id": program_id,
        "kind": "portfolio_diversification_challenger",
        "signal": {"alternative": alt, "fixed_weight": x.get("contract", {}).get("fixed_weight")},
        "timing": {
            "decision_cadence": "frozen challenger start plus monthly rebalance",
            "entry_rule": "establish the fixed challenger mix at its declared decision boundary",
            "holding_rule": "mark daily and rebalance only under the frozen monthly rule; do not chase one-day results",
        },
        "paper_action": pos,
        "action_text": f"Shadow {_weights_text(pos, 12)}.",
        "forward_days": days,
        "scorecard": {
            "challenger_cumulative_bps": _bp(challenger_nav) if admitted_nav(challenger_nav) else None,
            # Preserve legacy common-capital differences. Wealth ratios are
            # separate metrics, never substituted for the published fields.
            "matched_cost_basis": "BOTH_NET_IF_FLATTENED_NOW" if both_net else "UNADMITTED_OR_INCOMPLETE",
            "funded_nav_reconciliation": "PASS_THREE_BOOKS" if nav_reconciled else "FAIL_CLOSED",
            "challenger_absolute_net_if_flattened_now_bps": _bp(challenger_nav) if both_net else None,
            "incumbent_absolute_net_if_flattened_now_bps": _bp(incumbent_nav) if both_net else None,
            "matched_control_absolute_net_if_flattened_now_bps": _bp(matched_nav) if both_net else None,
            "challenger_vs_incumbent_relative_wealth_bps": _bp(incumbent_relative),
            "challenger_vs_matched_control_relative_wealth_bps": _bp(matched_relative),
            "excess_vs_incumbent_bps": _bp(fwd.get("challenger_minus_incumbent_cumulative")) if matched_complete else None,
            "excess_vs_matched_cash_control_bps": _bp(fwd.get("challenger_minus_matched_cumulative")) if matched_complete else None,
            "matched_observation_integrity": "COMPLETE" if matched_complete else "INCOMPLETE_FAIL_CLOSED",
            "vs_incumbent_observed_sessions": session_stats["vs_incumbent"]["observed_sessions"],
            "vs_incumbent_positive_sessions": session_stats["vs_incumbent"]["positive_sessions"],
            "vs_incumbent_session_hit_rate": session_stats["vs_incumbent"]["hit_rate"],
            "vs_matched_cash_control_observed_sessions": session_stats["vs_matched_cash_control"]["observed_sessions"],
            "vs_matched_cash_control_positive_sessions": session_stats["vs_matched_cash_control"]["positive_sessions"],
            "vs_matched_cash_control_session_hit_rate": session_stats["vs_matched_cash_control"]["hit_rate"],
            "max_drawdown": metrics.get("max_drawdown"),
            "annualized_vol": metrics.get("annualized_vol"),
        },
        "validation_grade": _grade(days) if matched_complete else "FORWARD_MATCHED_OBSERVATIONS_INCOMPLETE",
        "decision_use": (
            f"Tests whether allocating half the incumbent portfolio to {alt} improves capital efficiency and diversification. "
            "A market decision requires positive excess versus both the unchanged incumbent and matched BIL control with enough forward observations."
        ),
        "boundaries": x.get("boundaries", {}),
    }



def _p438_semiconductor_predecessor(x: dict[str, Any] | None) -> dict[str, Any]:
    """Compact an older immutable semiconductor forward identity without pooling it into the current cohort."""
    if not x:
        return {
            "present": False,
            "sample_combination_authorized": False,
        }
    frozen = x.get("frozen_prediction_identity") or {}
    rows = [row for row in (x.get("rows") or []) if isinstance(row, dict)]
    elapsed = [
        int(row.get("elapsed_close_to_close_sessions") or 0)
        for row in rows
        if row.get("elapsed_close_to_close_sessions") is not None
    ]
    remaining = [
        int(row.get("remaining_sessions_to_fixed20") or 0)
        for row in rows
        if row.get("remaining_sessions_to_fixed20") is not None
    ]
    latest = sorted(
        str(row.get("latest_common_date"))
        for row in rows
        if row.get("latest_common_date")
    )
    symbols = sorted(str(row.get("symbol")) for row in rows if row.get("symbol"))
    return {
        "present": True,
        "program_id": "P438_SEMICONDUCTOR_FORWARD_MTD_R1",
        "parent": x.get("parent"),
        "classification": x.get("classification"),
        "signal_date": frozen.get("generation_bar_date"),
        "execution_delay_sessions": frozen.get("delay_sessions"),
        "holding_horizon_sessions": frozen.get("hold_sessions"),
        "cost_bps": frozen.get("cost_bps"),
        "prediction_blob_sha": frozen.get("prediction_blob_sha"),
        "research_foundry_branch_commit": frozen.get("research_foundry_branch_commit"),
        "symbols": symbols,
        "latest_common_date": latest[-1] if latest else None,
        "elapsed_close_to_close_sessions": max(elapsed) if elapsed else None,
        "remaining_sessions_to_fixed20": max(remaining) if remaining else None,
        # String "false" and numeric 1 are not independently resolved outcomes.
        "all_rows_terminal": bool(rows) and all(row.get("final_target_resolved") is True for row in rows),
        "sample_combination_authorized": False,
        "combination_rule": (
            "Predecessor and current-cohort sessions may overlap in calendar time and have different frozen identities; "
            "never add their session counts or pool their outcomes without a preregistered cross-cohort aggregation rule."
        ),
    }


def _semiconductor_program_continuity(
    predecessor: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    dates = [
        str(value)
        for value in (
            predecessor.get("signal_date") if predecessor.get("present") else None,
            current.get("current_signal_date"),
        )
        if value
    ]
    return {
        "program_family": "SEMICONDUCTOR_FORWARD",
        "first_frozen_signal_date": min(dates) if dates else None,
        "predecessor": predecessor,
        "current_cohort": {
            "cohort_id": current.get("current_cohort_id"),
            "signal_date": current.get("current_signal_date"),
            "status": current.get("current_cohort_status"),
            "resolution": current.get("current_resolution"),
        },
        "program_clock_is_not_current_cohort_clock": True,
        "overlapping_sessions_are_not_additive": True,
        "reporting_rule": (
            "Show program-family age, predecessor identities, and current-cohort age separately. "
            "A newer cohort must not erase an older frozen forward identity."
        ),
    }


def _prospective_state(ledger: dict[str, Any] | None, program_id: str) -> dict[str, Any]:
    if ledger is None:
        return {"ledger_status": "NOT_SUPPLIED", "program_id": program_id}
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise RuntimeError(f"unexpected prospective ledger schema {ledger.get('schema')}")
    rows = [c for c in (ledger.get("cohorts") or []) if c.get("program_id") == program_id]
    summary = dict((ledger.get("summary") or {}).get(program_id) or {})
    # A summary is not independent cohort evidence. In particular, a caller-
    # supplied resolved_cohorts=20 must not mark a one-row frozen H20 sample
    # as reaching the stronger full-promotion floor.
    actual_registered = len(rows)
    actual_resolved = sum(c.get("status") == "RESOLVED" for c in rows)
    actual_open = sum(c.get("status") in {"REGISTERED", "AWAITING_ENTRY_SESSION", "OPEN", "PARTIALLY_RESOLVED"} for c in rows)
    actual_late = sum(c.get("status") == "LATE_REGISTRATION_REJECTED" for c in rows)
    actual_counts = (actual_registered, actual_resolved, actual_open, actual_late)
    reported_counts = (
        summary.get("registered_cohorts", actual_registered),
        summary.get("resolved_cohorts", actual_resolved),
        summary.get("open_cohorts", actual_open),
        summary.get("late_registration_rejections", actual_late),
    )
    if any(type(value) is not int for value in reported_counts) or reported_counts != actual_counts:
        raise ValueError(f"PROSPECTIVE_COHORT_SUMMARY_COUNT_MISMATCH:{program_id}")
    # The stronger full-promotion floor is an owning producer contract, not
    # caller-authored summary metadata (e.g. 1 replacing frozen fixed20).
    contract_floor = CONTRACTS.get(program_id, {}).get("minimum_resolved_for_promotion")
    reported_floor = summary.get("minimum_resolved_for_promotion", contract_floor)
    if type(reported_floor) is not type(contract_floor) or reported_floor != contract_floor:
        raise ValueError(f"PROSPECTIVE_COHORT_PROMOTION_FLOOR_MISMATCH:{program_id}")
    current = max(
        rows,
        key=lambda c: (str(c.get("signal_date") or ""), str(c.get("first_registered_at") or "")),
        default=None,
    )
    out = {
        "ledger_status": "PRESENT",
        "program_id": program_id,
        "market_data_asof": ledger.get("market_data_asof"),
        "registered_cohorts": actual_registered,
        "resolved_cohorts": actual_resolved,
        "open_cohorts": actual_open,
        "late_registration_rejections": actual_late,
        "minimum_resolved_for_promotion": contract_floor,
        "promotion_authority": False,
    }
    out["forward_science_stages"] = _separate_forward_science_stages(out)
    for key in (
        "resolved_observations",
        "positive_hit_rate",
        "mean_excess_vs_itb_bps",
        "mean_ticker_book_excess_vs_smh_bps",
        "mean_ticker_positive_hit_rate",
    ):
        if key in summary:
            out[key] = summary.get(key)
    if program_id == "SEMICONDUCTOR_SHARED_RIDGE":
        # Project only the exact already-resolved frozen cohort identities.
        # Keep legacy mixed-cost fields unchanged for existing consumers.
        resolved = [c for c in rows if c.get("status") == "RESOLVED"]
        expected = int(summary.get("resolved_cohorts", len(resolved)) or 0)
        projections = ledger.get("matched_after_cost_projections") or {}
        matched = []
        for cohort in resolved:
            projection = projections.get(str(cohort.get("cohort_id"))) or {}
            fields = (
                projection.get("ticker_minus_smh_net_bps"),
                projection.get("ticker_minus_equal_weight_13_net_bps"),
            )
            if (
                projection.get("status") != "DERIVED_FROM_FROZEN_RESOLVED_COHORT_NO_OUTCOME_BACKFILL"
                or projection.get("original_resolution_mutated") is not False
                or projection.get("alpha_or_promotion_authority") is not False
                or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in fields)
            ):
                break
            matched.append(tuple(float(v) for v in fields))
        complete = bool(resolved) and len(matched) == len(resolved) == expected
        out["matched_cost_projection_status"] = (
            "ALL_RESOLVED_COHORTS_DERIVED" if complete
            else "NO_RESOLVED_COHORT" if not resolved and expected == 0
            else "MATCHED_COST_PROJECTION_INCOMPLETE"
        )
        out["mean_ticker_book_excess_vs_smh_net_bps"] = (
            round(sum(v[0] for v in matched) / len(matched), 4) if complete else None
        )
        out["mean_ticker_book_excess_vs_equal_weight_13_net_bps"] = (
            round(sum(v[1] for v in matched) / len(matched), 4) if complete else None
        )
        out["legacy_mean_ticker_book_excess_vs_smh_basis"] = "BOOK_NET_VS_SMH_GROSS"
    if program_id == "HOMEBUILDERS":
        # The frozen Homebuilders contract charges stock round trips but
        # specifies no ITB/QQQ benchmark fee. Preserve the legacy mixed-cost
        # numbers, never fabricate a matched-net benchmark comparison.
        full = [c for c in rows if c.get("status") == "RESOLVED"]
        partial = [
            c for c in rows if c.get("status") == "PARTIALLY_RESOLVED"
            and any(isinstance(row, dict) and row.get("status") == "RESOLVED"
                    for row in ((c.get("resolution") or {}).get("observations") or []))
        ]
        reportable = full + partial
        expected_full = int(summary.get("resolved_cohorts", len(full)) or 0)
        projections = ledger.get("homebuilders_cost_basis_projections") or {}
        valid = 0
        for cohort in reportable:
            projection = projections.get(str(cohort.get("cohort_id"))) or {}
            legacy = projection.get("legacy_stock_net_minus_itb_gross_mean_bps")
            # A finite caller-supplied projection is not proof that it was
            # derived from THIS immutable cohort. Rebind the status label to
            # the original resolved rows; do not alter the original returns.
            resolution = cohort.get("resolution")
            observations = resolution.get("observations") if isinstance(resolution, dict) else None
            observations = observations if isinstance(observations, list) else []
            resolved_obs = [r for r in observations if isinstance(r, dict)
                            and r.get("status") == "RESOLVED"]
            fields = {
                "stock_net_mean_bps": "net_return_bps",
                "itb_gross_mean_bps": "itb_return_bps",
                "qqq_gross_mean_bps": "qqq_return_bps",
                "legacy_stock_net_minus_itb_gross_mean_bps": "excess_vs_itb_bps",
                "legacy_stock_net_minus_qqq_gross_mean_bps": "excess_vs_qqq_bps",
            }
            source_numeric = all(
                isinstance(r.get(field), (int, float))
                and not isinstance(r.get(field), bool)
                and math.isfinite(r[field])
                for r in resolved_obs for field in fields.values()
            )
            source_bound = (
                bool(resolved_obs)
                and source_numeric
                and projection.get("resolved_observations") == len(resolved_obs)
                and isinstance(cohort.get("stock_round_trip_cost_bps"), (int, float))
                and not isinstance(cohort.get("stock_round_trip_cost_bps"), bool)
                and math.isfinite(cohort["stock_round_trip_cost_bps"])
                and projection.get("stock_round_trip_cost_bps") == float(cohort["stock_round_trip_cost_bps"])
                and all(
                    projection.get(projected) == round(
                        sum(float(r[source]) for r in resolved_obs) / len(resolved_obs), 4
                    )
                    for projected, source in fields.items()
                )
                and (
                    (cohort.get("status") == "RESOLVED" and len(resolved_obs) == len(observations))
                    or (cohort.get("status") == "PARTIALLY_RESOLVED"
                        and len(resolved_obs) < len(observations))
                )
            )
            if (
                source_bound
                and projection.get("status") == "DERIVED_MIXED_COST_ONLY_BENCHMARK_FEES_UNFROZEN"
                and projection.get("original_resolution_mutated") is False
                and projection.get("alpha_or_promotion_authority") is False
                and projection.get("matched_stock_net_minus_itb_net_mean_bps") is None
                and isinstance(legacy, (int, float)) and not isinstance(legacy, bool)
                and math.isfinite(legacy)
            ):
                valid += 1
        complete = bool(reportable) and valid == len(reportable) and len(full) == expected_full
        out["homebuilders_cost_basis_projection_status"] = (
            "ALL_REPORTABLE_PARTIAL_COHORTS_MIXED_COST_LABELLED" if complete and partial
            else "ALL_RESOLVED_COHORTS_MIXED_COST_LABELLED" if complete
            else "NO_RESOLVED_OBSERVATIONS" if not reportable and expected_full == 0
            else "MIXED_COST_PROJECTION_INCOMPLETE"
        )
        out["legacy_mean_excess_vs_itb_basis"] = "STOCK_NET_MINUS_ITB_GROSS_NOT_MATCHED_AFTER_COST"
        out["mean_matched_after_cost_excess_vs_itb_bps"] = None
        out["mean_matched_after_cost_excess_vs_qqq_bps"] = None
        out["homebuilders_observation_unit"] = "PER_SYMBOL_FROZEN_HORIZON_MEAN_NOT_FUNDED_PORTFOLIO"
        out["homebuilders_funded_portfolio_nav_return_bps"] = None
    if current:
        out.update(
            {
                "current_cohort_id": current.get("cohort_id"),
                "current_signal_date": current.get("signal_date"),
                "current_cohort_status": current.get("status"),
            }
        )
        resolution = current.get("resolution") or {}
        compact = {}
        for key in (
            "entry_date",
            "exit_date",
            "horizon_sessions",
            "sessions_completed",
            "ticker_book_net_return_bps",
            "ticker_book_excess_vs_smh_bps",
            "ticker_book_excess_vs_qqq_bps",
            "ticker_positive_hit_rate",
            "prediction_mae_bps",
        ):
            if key in resolution:
                compact[key] = resolution.get(key)
        if resolution.get("summary") is not None:
            compact["summary"] = resolution.get("summary")
        if resolution.get("current_mark_metrics") is not None:
            compact["current_mark_metrics"] = resolution.get("current_mark_metrics")
        if (
            program_id == "SEMICONDUCTOR_SHARED_RIDGE"
            and current.get("status") == "RESOLVED"
            and out.get("matched_cost_projection_status") == "ALL_RESOLVED_COHORTS_DERIVED"
        ):
            projection = (ledger.get("matched_after_cost_projections") or {}).get(str(current.get("cohort_id")))
            compact["matched_after_cost"] = {
                "ticker_minus_smh_net_bps": projection["ticker_minus_smh_net_bps"],
                "ticker_minus_equal_weight_13_net_bps": projection["ticker_minus_equal_weight_13_net_bps"],
                "original_resolution_mutated": False,
                "alpha_or_promotion_authority": False,
            }
        if compact:
            out["current_resolution"] = compact
        if current.get("source_health") is not None:
            out["source_health"] = current.get("source_health")
    return out


def _separate_forward_science_stages(state: dict[str, Any]) -> dict[str, Any]:
    """Expose observation and stronger sample breadth without canary gate invention."""
    resolved = int(state.get("resolved_cohorts", 0) or 0)
    floor = state.get("minimum_resolved_for_promotion")
    return {
        "resolved_cohort_count": resolved,
        "forward_sanity_stage": (
            "RESOLVED_COHORT_OBSERVED_ISSUER_ENVELOPE_PENDING"
            if resolved > 0 else "NO_RESOLVED_COHORT"
        ),
        "live_canary_eligibility_stage": "INDEPENDENT_OWNER_ADJUDICATION_REQUIRED",
        "live_probation_stage": "INDEPENDENT_OWNER_ADJUDICATION_REQUIRED",
        "full_promotion_sample_floor": floor,
        "full_promotion_sample_floor_reached": (
            floor is not None and resolved >= int(floor)
        ),
        "promotion_authority": False,
    }


def _prospective_evidence_grade(state: dict[str, Any]) -> str:
    if state.get("ledger_status") != "PRESENT":
        return "NO_PROSPECTIVE_LEDGER"
    if int(state.get("late_registration_rejections", 0) or 0) > 0:
        return "CHRONOLOGY_REJECTION_PRESENT"
    if int(state.get("registered_cohorts", 0) or 0) <= 0:
        return "NO_REGISTERED_PROSPECTIVE_COHORT"
    status = str(state.get("current_cohort_status") or "")
    if status in {"REGISTERED", "AWAITING_ENTRY_SESSION", "OPEN", "PARTIALLY_RESOLVED"}:
        return f"PROSPECTIVE_{status}"
    resolved = int(state.get("resolved_cohorts", 0) or 0)
    floor = state.get("minimum_resolved_for_promotion")
    if floor is not None and resolved < int(floor):
        return "PROSPECTIVE_EVIDENCE_ACCUMULATING"
    if floor is not None and resolved >= int(floor):
        return "SAMPLE_FLOOR_REACHED_NOT_PROMOTED"
    if resolved > 0:
        return "PROSPECTIVE_RESULTS_AVAILABLE"
    return "PROSPECTIVE_REGISTERED"


def _native_lane(x: dict[str, Any], prospective: dict[str, Any] | None = None) -> dict[str, Any]:
    program_id = str(x["program_id"])
    validation = x.get("validation") or {}
    action = x.get("paper_action") or {}
    action_status = str(action.get("status") or "NATIVE_SIGNAL")
    if program_id == "SEMICONDUCTOR_SHARED_RIDGE":
        state = str(validation.get("state") or "")
        grade = "PROSPECTIVE_SIGNAL_READY" if state == "PROSPECTIVE_ELIGIBLE" else "DESCRIPTIVE_PRESTART"
        action_text = (
            f"Daily +1/fixed20 cohort. Positive breadth {float((x.get('signal') or {}).get('positive_breadth', 0)):.1%}; "
            f"paper action status {action_status}."
        )
    elif program_id == "HOMEBUILDERS":
        grade = "PROSPECTIVE_DIAGNOSTIC"
        admitted = (x.get("signal") or {}).get("admitted_symbols") or []
        horizons = (x.get("signal") or {}).get("duration_horizon_sessions_by_symbol") or {}
        action_text = f"Admitted {', '.join(admitted) or 'none'}; next-session accounting with frozen 5/60-session horizons {horizons}."
    else:
        grade = "CORROBORATION_ONLY"
        positive = (x.get("signal") or {}).get("positive_symbols") or []
        negative = (x.get("signal") or {}).get("negative_symbols") or []
        action_text = f"Corroborate/watch positives {', '.join(positive) or 'none'}; negatives {', '.join(negative) or 'none'}; no frozen allocation book."
    return {
        "program_id": program_id,
        "kind": x.get("kind"),
        "signal_date": x.get("signal_date"),
        "signal": x.get("signal", {}),
        "timing": x.get("timing", {}),
        "paper_action": action,
        "action_text": action_text,
        "benchmarks": x.get("benchmarks", []),
        "scorecard": x.get("scorecard"),
        "validation": validation,
        "validation_grade": grade,
        "prospective_evidence": prospective or {"ledger_status": "NOT_SUPPLIED", "program_id": program_id},
        "evidence_grade": _prospective_evidence_grade(prospective or {}),
        "forward_science_stages": _separate_forward_science_stages(prospective or {}),
        "decision_use": x.get("decision_use"),
        "boundaries": x.get("boundaries", {}),
    }


def _decision_chain(lanes: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(x.get("program_id")): x for x in lanes}
    p46 = by_id.get("P46", {})
    semi = by_id.get("SEMICONDUCTOR_SHARED_RIDGE", {})
    hb = by_id.get("HOMEBUILDERS", {})
    large = by_id.get("GENERALIZED_LARGECAP_RIDGE", {})
    p249 = by_id.get("P249_P266", {})
    p558 = by_id.get("P558", {})
    clo = by_id.get("SENIOR_CLO", {})
    return {
        "regime": {
            "source": "P46",
            "selected": (p46.get("signal") or {}).get("selected", []),
            "authority": "context_only" if not p46.get("scientific_forward_credit") else "forward_validated_context",
        },
        "sectors": {
            "semiconductor": {
                "positive_breadth": (semi.get("signal") or {}).get("positive_breadth"),
                "action": (semi.get("paper_action") or {}).get("status"),
                "prospective_evidence": semi.get("prospective_evidence", {}),
                "evidence_grade": semi.get("evidence_grade"),
            },
            "homebuilders": {
                "admitted": (hb.get("signal") or {}).get("admitted_symbols", []),
                "horizons": (hb.get("signal") or {}).get("duration_horizon_sessions_by_symbol", {}),
                "prospective_evidence": hb.get("prospective_evidence", {}),
                "evidence_grade": hb.get("evidence_grade"),
            },
        },
        "tickers": {
            "semiconductor_positive": (semi.get("signal") or {}).get("positive_symbols", []),
            "largecap_positive_corroboration": (large.get("signal") or {}).get("positive_symbols", []),
            "largecap_negative_corroboration": (large.get("signal") or {}).get("negative_symbols", []),
        },
        "portfolio": {
            "source": "P249_P266",
            "target_weights": p249.get("paper_action", {}),
            "validation_grade": p249.get("validation_grade"),
        },
        "diversification": {
            "KMLM": p558.get("scorecard", {}),
            "JAAA": clo.get("scorecard", {}),
        },
        "realized_excess": {
            "p266_increment_bps": (p249.get("scorecard") or {}).get("p266_increment_cumulative_bps"),
            "KMLM_vs_incumbent_bps": (p558.get("scorecard") or {}).get("excess_vs_incumbent_bps"),
            "KMLM_vs_cash_control_bps": (p558.get("scorecard") or {}).get("excess_vs_matched_cash_control_bps"),
            "JAAA_vs_incumbent_bps": (clo.get("scorecard") or {}).get("excess_vs_incumbent_bps"),
            "JAAA_vs_cash_control_bps": (clo.get("scorecard") or {}).get("excess_vs_matched_cash_control_bps"),
            "semiconductor_mean_ticker_book_excess_vs_smh_bps": (semi.get("prospective_evidence") or {}).get("mean_ticker_book_excess_vs_smh_bps"),
            "semiconductor_legacy_smh_comparison_basis": (semi.get("prospective_evidence") or {}).get("legacy_mean_ticker_book_excess_vs_smh_basis"),
            "semiconductor_mean_ticker_book_excess_vs_smh_net_bps": (semi.get("prospective_evidence") or {}).get("mean_ticker_book_excess_vs_smh_net_bps"),
            "semiconductor_mean_ticker_book_excess_vs_equal_weight_13_net_bps": (semi.get("prospective_evidence") or {}).get("mean_ticker_book_excess_vs_equal_weight_13_net_bps"),
            "semiconductor_matched_cost_projection_status": (semi.get("prospective_evidence") or {}).get("matched_cost_projection_status"),
            "homebuilders_mean_excess_vs_itb_bps": (hb.get("prospective_evidence") or {}).get("mean_excess_vs_itb_bps"),
            "homebuilders_legacy_itb_cost_basis": (hb.get("prospective_evidence") or {}).get("legacy_mean_excess_vs_itb_basis"),
            "homebuilders_matched_after_cost_status": (hb.get("prospective_evidence") or {}).get("homebuilders_cost_basis_projection_status"),
            "homebuilders_matched_after_cost_excess_vs_itb_bps": (hb.get("prospective_evidence") or {}).get("mean_matched_after_cost_excess_vs_itb_bps"),
            "homebuilders_observation_unit": (hb.get("prospective_evidence") or {}).get("homebuilders_observation_unit"),
            "homebuilders_funded_portfolio_nav_return_bps": (hb.get("prospective_evidence") or {}).get("homebuilders_funded_portfolio_nav_return_bps"),
        },
        "resulting_market_decision_rule": (
            "Use P249/P266 as the frozen base research portfolio; treat P46 as regime context; add only native prospectively "
            "authorized cohorts such as Semiconductor three-book cohorts; use Homebuilders and generalized large-cap transport "
            "as decision evidence until a frozen sizing book exists; do not promote KMLM/JAAA substitutions until excess evidence is sufficient."
        ),
    }


def _load_prospective_ledger(root: Path) -> dict[str, Any] | None:
    """Use the freshly resolved ledger, never the prior-current history copy.

    The report job intentionally stages both a historical main snapshot under
    prior-current/ and a newly resolved producer under prospective-current/.
    They are different authorities, not conflicting copies of one current
    artifact. Conflicting duplicates *within* the selected current producer
    directory still fail closed through _load.
    """
    name = "forward_prospective_cohort_ledger_r1.json"
    current = root / "prospective-current"
    if current.is_dir():
        if not (current / name).is_file():
            raise ValueError("CURRENT_PROSPECTIVE_LEDGER_NOT_MATERIALIZED")
        return _load(current, name)
    if (root / "prior-current" / name).is_file():
        raise ValueError("CURRENT_PROSPECTIVE_LEDGER_NOT_MATERIALIZED")
    return _load(root, name)


def build(root: Path) -> dict[str, Any]:
    ledger = _load_prospective_ledger(root)
    p438_predecessor = _p438_semiconductor_predecessor(
        _load(root, "p438_semiconductor_forward_mtd_r1.json")
    )
    lanes = [
        _p46(_load(root, "p46_forward_observation_v2.json")),
        _p249(_load(root, "forward_p249_p266_shadow_r1.json")),
        _challenger(_load(root, "forward_p558_current_core_shadow_r1.json"), "P558", "KMLM"),
        _challenger(_load(root, "forward_senior_clo_current_core_shadow_r1.json"), "SENIOR_CLO", "JAAA"),
    ]
    native = _load_native_adapters(root)
    for program_id in EXPECTED_PRIVATE_ADAPTERS:
        payload = native.get(program_id)
        if payload:
            lanes.append(_native_lane(payload, _prospective_state(ledger, program_id)))
        else:
            lanes.append({
                "program_id": program_id,
                "status": "ADAPTER_RESULT_NOT_PRESENT",
                "validation_grade": "NO_CURRENT_NATIVE_RESULT",
                "decision_use": "Adapter contract exists; current sanitized native result has not been supplied to this report run.",
            })

    semi_lane = next((row for row in lanes if row.get("program_id") == "SEMICONDUCTOR_SHARED_RIDGE"), None)
    semi_prospective = (
        semi_lane.get("prospective_evidence", {})
        if isinstance(semi_lane, dict)
        else _prospective_state(ledger, "SEMICONDUCTOR_SHARED_RIDGE")
    )
    semiconductor_continuity = _semiconductor_program_continuity(
        p438_predecessor,
        semi_prospective,
    )
    if isinstance(semi_lane, dict):
        semi_lane["program_continuity"] = semiconductor_continuity

    actionable_context = []
    for lane in lanes:
        if lane.get("program_id") == "P46" and lane.get("signal", {}).get("selected"):
            actionable_context.append({
                "source": "P46",
                "intel": "Cross-asset relative preference",
                "state": lane["signal"]["selected"],
                "authority": "context_only" if not lane.get("scientific_forward_credit") else "forward_validated_context",
            })
        if lane.get("program_id") == "P249_P266" and lane.get("paper_action"):
            actionable_context.append({
                "source": "P249_P266",
                "intel": "Current frozen portfolio expression",
                "state": lane["paper_action"],
                "authority": "research_shadow_only",
            })
        if lane.get("program_id") in EXPECTED_PRIVATE_ADAPTERS and lane.get("signal"):
            actionable_context.append({
                "source": lane["program_id"],
                "intel": lane.get("kind"),
                "state": lane.get("signal"),
                "authority": "research_only_native_semantics",
            })

    missing = [p for p in EXPECTED_PRIVATE_ADAPTERS if p not in native]
    p249_lane = next((x for x in lanes if x.get("program_id") == "P249_P266"), {})
    p249_health = p249_lane.get("source_health") or {}
    ledger_freshness = {} if ledger is None else (ledger.get("freshness") or {})
    market_data_dates = [
        str(value)[:10]
        for value in (
            p249_health.get("latest_scored_common_session"),
            None if ledger is None else ledger.get("market_data_asof"),
        )
        if value
    ]
    common_asof = min(market_data_dates) if market_data_dates else None
    # A ledger can be internally cross-symbol synchronized while every
    # program's latest historical source date lags an independently observed
    # completed market session. Do not present that as a fresh forward source.
    def strict_session_day(value: Any):
        # Never silently truncate malformed timestamps into valid-looking dates.
        if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None

    completed_reference = p249_health.get("latest_scored_common_session")
    reference_day = strict_session_day(completed_reference)
    reference_state = (
        "OBSERVED_COMPLETED_SESSION" if reference_day is not None
        else "INVALID_INDEPENDENT_COMPLETED_SESSION"
        if completed_reference not in (None, "") else "NO_INDEPENDENT_COMPLETED_SESSION"
    )
    forward_source_lag = {}
    terminal_cohort_source_snapshots = {}
    cohort_rows = (ledger or {}).get("cohorts") or []
    # Terminal cohorts deliberately preserve their original exit-tape/source
    # snapshot. Only unresolved cohorts need a current completed-session tape.
    # Missing/malformed lineage stays fail-closed as an active freshness risk.
    cohort_rows = cohort_rows if isinstance(cohort_rows, list) else []
    for program, health in (ledger_freshness.get("source_health_by_program") or {}).items():
        if not isinstance(health, dict):
            forward_source_lag[program] = {"state": "INVALID_SOURCE_HEALTH"}
            continue
        source_max = health.get("source_max_date")
        source_day = strict_session_day(source_max)
        if source_day is None:
            # Do not reflect malformed, potentially sensitive raw values.
            forward_source_lag[program] = {"state": "INVALID_SOURCE_DATE"}
            continue
        if reference_day is None:
            continue
        if source_day < reference_day:
            program_rows = [
                row for row in cohort_rows
                if isinstance(row, dict) and row.get("program_id") == program
            ]
            # Do not bless a caller-supplied RESOLVED label alone. Require
            # each frozen terminal exit to be covered by a synchronized tape.
            terminal_exits = []
            for row in program_rows:
                if row.get("status") != "RESOLVED":
                    break
                resolution = row.get("resolution")
                if not isinstance(resolution, dict):
                    break
                exits = (
                    [resolution.get("exit_date")]
                    if program != "HOMEBUILDERS" else
                    [obs.get("exit_date") for obs in (resolution.get("observations") or [])
                     if isinstance(obs, dict) and obs.get("status") == "RESOLVED"]
                )
                if not exits or any(strict_session_day(value) is None for value in exits):
                    break
                terminal_exits.extend(strict_session_day(value) for value in exits)
            else:
                if (program_rows and terminal_exits
                        and health.get("all_symbols_share_latest_date") is True
                        and health.get("lagging_symbols_vs_source_max") == []
                        and max(terminal_exits) <= source_day):
                    terminal_cohort_source_snapshots[program] = {
                        "state": "FROZEN_TERMINAL_COHORT_SOURCE_HISTORY_NOT_ACTIVE_STALENESS",
                        "source_max_date": source_max,
                        "observed_completed_reference_session": completed_reference,
                        "terminal_cohort_count": len(program_rows),
                    }
                    continue
            forward_source_lag[program] = {
                "state": "SOURCE_HISTORY_BEHIND_OBSERVED_COMPLETED_SESSION",
                "source_max_date": source_max,
                "observed_completed_reference_session": completed_reference,
            }
    freshness = {
        "common_market_data_asof": common_asof,
        "p249_p266_source_health": p249_health,
        "prospective_ledger": ledger_freshness,
        "forward_source_lag_vs_observed_completed_session": forward_source_lag,
        "terminal_cohort_source_snapshots": terminal_cohort_source_snapshots,
        "forward_source_reference_state": reference_state,
        "freshness_gap_visible": bool(
            p249_health.get("common_session_lags_source_max")
            or p249_health.get("unresolved_forward_gap") is not None
            or ledger_freshness.get("freshness_gap_visible")
            or p249_health.get("lagging_symbols_vs_source_max")
            or ledger_freshness.get("lagging_symbols_by_program")
            or forward_source_lag
            or reference_day is None
        ),
        "rule": "A successful workflow is not sufficient freshness proof. Consumers must compare the common market-data date with the expected completed exchange session and inspect per-symbol source health.",
    }
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Daily/on-demand forward validation and market-decision reporting across frozen research survivors.",
        "lanes": lanes,
        "program_continuity": {
            "SEMICONDUCTOR_FORWARD": semiconductor_continuity,
        },
        "market_decision_context": actionable_context,
        "decision_chain": _decision_chain(lanes),
        "freshness": freshness,
        "coverage": {
            "scored_now": [x.get("program_id") for x in lanes if x.get("signal")],
            "adapter_contracts_ready": list(EXPECTED_PRIVATE_ADAPTERS),
            "native_result_gaps": missing,
            "prospective_ledger": {
                "present": ledger is not None,
                "market_data_asof": None if ledger is None else ledger.get("market_data_asof"),
                "programs": [] if ledger is None else sorted((ledger.get("summary") or {}).keys()),
            },
            "predecessor_forward_identities": {
                "P438_SEMICONDUCTOR_FORWARD_MTD_R1": p438_predecessor.get("present") is True,
            },
        },
        "interpretation": {
            "weight_is_not_forecast": True,
            "positive_model_score_is_not_position_size": True,
            "forward_score_requires_matched_benchmark_or_control": True,
            "small_samples_are_not_promotion_evidence": True,
            "daily_score_does_not_imply_daily_turnover": True,
            "prospective_evidence_does_not_grant_allocation_authority": True,
            "program_clock_is_not_current_cohort_clock": True,
            "overlapping_forward_cohort_sessions_are_not_additive": True,
            "broker_or_live_authority": False,
        },
    }


def self_test() -> None:
    import tempfile

    # Source-only truthiness falsifiers: a syntactically valid JSON string
    # must not become scientific credit or a resolved predecessor cohort.
    for flag in ("false", "true", 1, 0, None, [], {}):
        p46 = _p46({"decision": {"scientific_forward_credit_authorized": flag}})
        assert p46["scientific_forward_credit"] is False
        assert p46["validation_grade"] == "SHAKEDOWN_ONLY"
        p438 = _p438_semiconductor_predecessor({"rows": [{"final_target_resolved": flag}]})
        assert p438["all_rows_terminal"] is False
    assert _p46({"decision": {"scientific_forward_credit_authorized": True}})["scientific_forward_credit"] is True
    assert _p438_semiconductor_predecessor({"rows": [{"final_target_resolved": True}]})["all_rows_terminal"] is True

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "p46_forward_observation_v2.json").write_text(json.dumps({
            "decision": {"selected": ["DBC", "QQQ"], "scores": {"DBC": 0.85}, "target_weights": {"DBC": 0.5, "QQQ": 0.5}, "scientific_forward_credit_authorized": False},
            "operational_shadow": {"anchor_date": "2026-09-09", "latest_date": "2026-09-09"},
        }))
        (root / "forward_p249_p266_shadow_r1.json").write_text(json.dumps({
            "current_state": {"p249_core": {"SOXX": 0.4}, "p266": {"XBI": 1.0}, "p249_plus_p266": {"SOXX": 0.3, "XBI": 0.1}},
            "source_health": {"source_max_date": "2026-09-13", "latest_scored_common_session": "2026-09-12", "lagging_symbols_vs_source_max": ["XBI"], "common_session_lags_source_max": True},
            "forward": {"p249_core_net": {"cumulative_return": 0.01}, "p249_plus_p266_net": {"cumulative_return": 0.009, "days": 2}, "satellite_increment_cumulative": -0.001},
        }))
        semi = {
            "schema": ADAPTER_SCHEMA,
            "program_id": "SEMICONDUCTOR_SHARED_RIDGE",
            "kind": "daily_entry_value_with_three_book_expression",
            "signal_date": "2026-09-10",
            "signal": {"positive_symbols": ["AMAT"], "positive_breadth": 0.5},
            "timing": {"execution_delay_sessions": 1, "holding_horizon_sessions": 20},
            "paper_action": {"status": "PAPER_COHORT_READY"},
            "validation": {"state": "PROSPECTIVE_ELIGIBLE"},
        }
        hb = {
            "schema": ADAPTER_SCHEMA,
            "program_id": "HOMEBUILDERS",
            "kind": "entry_admission_plus_adaptive_duration",
            "signal_date": "2026-09-10",
            "signal": {"admitted_symbols": ["CCS"], "duration_horizon_sessions_by_symbol": {"CCS": 5}},
            "timing": {"execution_delay_sessions": 1, "candidate_holding_horizons_sessions": [5, 60]},
            "paper_action": {"status": "OBSERVATION_ONLY_NO_FROZEN_SIZING_AUTHORITY"},
            "validation": {"state": "PROSPECTIVE_DIAGNOSTIC_NO_PROMOTION"},
        }
        large = {
            "schema": ADAPTER_SCHEMA,
            "program_id": "GENERALIZED_LARGECAP_RIDGE",
            "kind": "target_excluded_transport_corroboration",
            "signal_date": "2026-09-10",
            "signal": {"positive_symbols": ["CAT"], "negative_symbols": ["MSFT"]},
            "timing": {"execution_delay_sessions": 1, "holding_horizon_sessions": 20},
            "paper_action": {"status": "CORROBORATION_ONLY_NO_FROZEN_BOOK"},
            "validation": {"state": "TRANSPORT_FORWARD_OBSERVATION"},
        }
        for i, payload in enumerate((semi, hb, large)):
            (root / f"forward_program_adapter_{i}.json").write_text(json.dumps(payload))
        (root / "forward_prospective_cohort_ledger_r1.json").write_text(json.dumps({
            "schema": LEDGER_SCHEMA,
            "market_data_asof": "2026-09-13",
            "freshness": {"freshness_gap_visible": False, "lagging_symbols_by_program": {}},
            "cohorts": [
                {"cohort_id": "HOMEBUILDERS:2026-09-10:test", "program_id": "HOMEBUILDERS", "signal_date": "2026-09-10", "first_registered_at": "2026-09-11T00:00:00+00:00", "status": "OPEN", "resolution": {"entry_date": "2026-09-11", "sessions_completed": 1}},
                {"cohort_id": "SEMICONDUCTOR_SHARED_RIDGE:2026-09-10:test", "program_id": "SEMICONDUCTOR_SHARED_RIDGE", "signal_date": "2026-09-10", "first_registered_at": "2026-09-11T00:00:00+00:00", "status": "AWAITING_ENTRY_SESSION", "resolution": None},
            ],
            "summary": {
                "HOMEBUILDERS": {"registered_cohorts": 1, "resolved_cohorts": 0, "open_cohorts": 1, "late_registration_rejections": 0, "minimum_resolved_for_promotion": None, "resolved_observations": 0, "mean_excess_vs_itb_bps": None},
                "SEMICONDUCTOR_SHARED_RIDGE": {"registered_cohorts": 1, "resolved_cohorts": 0, "open_cohorts": 1, "late_registration_rejections": 0, "minimum_resolved_for_promotion": 20, "mean_ticker_book_excess_vs_smh_bps": None},
            },
        }))
        (root / "p438_semiconductor_forward_mtd_r1.json").write_text(json.dumps({
            "schema": "research.p438_semiconductor_forward_mtd_r1.v1",
            "workload_id": "P438_SEMICONDUCTOR_FORWARD_MTD_R1",
            "parent": "SEMICONDUCTOR_PREDICTED_VALUE_SCARCITY_FORWARD",
            "frozen_prediction_identity": {
                "research_foundry_branch_commit": "a" * 40,
                "prediction_blob_sha": "b" * 40,
                "generation_bar_date": "2026-09-04",
                "delay_sessions": 1,
                "hold_sessions": 20,
                "cost_bps": 25.0,
            },
            "classification": "FIXED20_TARGET_UNRESOLVED__DESCRIPTIVE_PATH_ONLY",
            "rows": [{
                "symbol": "AMAT",
                "latest_common_date": "2026-09-13",
                "elapsed_close_to_close_sessions": 4,
                "remaining_sessions_to_fixed20": 16,
                "final_target_resolved": False,
            }],
        }))
        out = build(root)
        assert out["schema"] == SCHEMA
        assert out["lanes"][0]["validation_grade"] == "SHAKEDOWN_ONLY"
        assert out["lanes"][1]["economic_current_admitted"] is False
        assert out["lanes"][1]["validation_grade"] == "ECONOMIC_SOURCE_NOT_ADMITTED"
        assert all(v is None for v in out["lanes"][1]["scorecard"].values())
        assert _funded_excess_metrics(-0.04, 0.17) == (0.21875, 0.20999999999999996) or (
            abs(_funded_excess_metrics(-0.04, 0.17)[0] - 0.21875) < 1e-12
            and abs(_funded_excess_metrics(-0.04, 0.17)[1] - 0.21) < 1e-12
        )
        assert _funded_excess_metrics(-1.0, 0.17) == (None, None)
        synthetic = {
            "schema": "research.forward_p249_p266_shadow_r1",
            "parent": "P249/P266/P278",
            "workload_id": "FORWARD_P249_P266_SHADOW_R1",
            "status": "FORWARD_OBSERVING",
            "source_health": {"unresolved_forward_gap": None, "latest_scored_common_session": "2026-09-11"},
            "forward": {
                "economic_continuity_verified": True, "latest_close": "2026-09-11",
                "observations": [{"date": "2026-09-10", "satellite_increment_net": 0.1}, {"date": "2026-09-11", "satellite_increment_net": 0.1}],
                "p249_core_net": {"days": 2, "cumulative_return": -0.04},
                "p249_plus_p266_net": {"days": 2, "cumulative_return": 0.17},
                "satellite_increment_cumulative": 0.22,
            },
            "current_state": {"p249_core": {"SOXX": 1.0}, "p266": {"XBI": 1.0}, "p249_plus_p266": {"XBI": 1.0}},
        }
        funded = _p249(synthetic)
        assert funded["economic_current_admitted"] is True
        assert funded["scorecard"]["p266_relative_wealth_excess_bps"] == 2187.5
        assert funded["scorecard"]["p266_increment_cumulative_bps"] == 2187.5
        assert funded["scorecard"]["p266_cumulative_return_difference_bps"] == 2100.0
        assert funded["scorecard"]["p266_legacy_compounded_daily_spread_bps"] == 2200.0
        assert funded["scorecard"]["p266_increment_metric_semantics"] == "CONSTANT_TARGET_SHADOW_COMBO_NAV_OVER_CORE_NAV_MINUS_ONE"
        assert funded["scorecard"]["p266_execution_limit"] == "IMPLICIT_DAILY_TARGET_RESET_WITH_UNPRICED_INTRAMONTH_TURNOVER"
        assert "reapplies target weights daily" in funded["timing"]["holding_rule"]
        assert "not trade or funded rebalance evidence" in funded["timing"]["entry_rule"]
        stats = _challenger_session_stats({
            "challenger_if_flattened_now": {"days": 2},
            "challenger_observations": [
                {"date": "2026-09-10", "net_return": 0.02, "core_return": 0.01},
                {"date": "2026-09-11", "net_return": -0.01, "core_return": 0.0},
            ],
            "matched_control_observations": [
                {"date": "2026-09-10", "net_return": 0.015},
                {"date": "2026-09-11", "net_return": -0.02},
            ],
        })
        assert stats["vs_incumbent"] == {"observed_sessions": 2, "positive_sessions": 1, "hit_rate": 0.5}
        assert stats["vs_matched_cash_control"] == {"observed_sessions": 2, "positive_sessions": 2, "hit_rate": 1.0}
        assert stats["complete"] is True
        incomplete = {
            "challenger_if_flattened_now": {"days": 2},
            "challenger_observations": [
                {"date": "2026-09-10", "net_return": 0.02, "core_return": 0.01},
                {"date": "2026-09-11", "net_return": -0.01, "core_return": 0.0},
            ],
            "matched_control_observations": [
                {"date": "2026-09-10", "net_return": 0.015},
            ],
            "challenger_minus_matched_cumulative": 0.99,
            "challenger_minus_incumbent_cumulative": 0.88,
        }
        assert _challenger_session_stats(incomplete)["complete"] is False
        guarded = _challenger({"forward": incomplete}, "P558", "KMLM")
        assert guarded["validation_grade"] == "FORWARD_MATCHED_OBSERVATIONS_INCOMPLETE"
        assert guarded["scorecard"]["matched_observation_integrity"] == "INCOMPLETE_FAIL_CLOSED"
        assert guarded["scorecard"]["excess_vs_matched_cash_control_bps"] is None
        assert guarded["scorecard"]["excess_vs_incumbent_bps"] is None
        duplicate = dict(incomplete)
        duplicate["matched_control_observations"] = [
            {"date": "2026-09-10", "net_return": 0.015},
            {"date": "2026-09-10", "net_return": -0.02},
        ]
        assert _challenger_session_stats(duplicate)["complete"] is False
        missing_numeric = dict(incomplete)
        missing_numeric["matched_control_observations"] = [
            {"date": "2026-09-10", "net_return": 0.015},
            {"date": "2026-09-11"},
        ]
        assert _challenger_session_stats(missing_numeric)["complete"] is False
        derived_overflow = dict(incomplete)
        derived_overflow["challenger_observations"] = [
            {"date": "2026-09-10", "net_return": 1e308, "core_return": -1e308},
            {"date": "2026-09-11", "net_return": 0.0, "core_return": 0.0},
        ]
        derived_overflow["matched_control_observations"] = [
            {"date": "2026-09-10", "net_return": -1e308},
            {"date": "2026-09-11", "net_return": 0.0},
        ]
        assert _challenger_session_stats(derived_overflow)["complete"] is False
        assert out["coverage"]["native_result_gaps"] == []
        assert out["decision_chain"]["sectors"]["homebuilders"]["horizons"] == {"CCS": 5}
        native_by_id = {x["program_id"]: x for x in out["lanes"]}
        assert native_by_id["HOMEBUILDERS"]["evidence_grade"] == "PROSPECTIVE_OPEN"
        assert native_by_id["SEMICONDUCTOR_SHARED_RIDGE"]["evidence_grade"] == "PROSPECTIVE_AWAITING_ENTRY_SESSION"
        assert native_by_id["SEMICONDUCTOR_SHARED_RIDGE"]["validation_grade"] == "PROSPECTIVE_SIGNAL_READY"
        assert native_by_id["SEMICONDUCTOR_SHARED_RIDGE"]["forward_science_stages"]["resolved_cohort_count"] == 0
        one = _separate_forward_science_stages({"resolved_cohorts": 1, "minimum_resolved_for_promotion": 20})
        assert one["forward_sanity_stage"] == "RESOLVED_COHORT_OBSERVED_ISSUER_ENVELOPE_PENDING"
        assert one["full_promotion_sample_floor_reached"] is False
        assert one["live_canary_eligibility_stage"] == "INDEPENDENT_OWNER_ADJUDICATION_REQUIRED"
        twenty = _separate_forward_science_stages({"resolved_cohorts": 20, "minimum_resolved_for_promotion": 20})
        assert twenty["full_promotion_sample_floor_reached"] is True
        assert twenty["promotion_authority"] is False
        assert out["coverage"]["prospective_ledger"]["present"] is True
        assert out["freshness"]["freshness_gap_visible"] is True
        assert out["freshness"]["p249_p266_source_health"]["lagging_symbols_vs_source_max"] == ["XBI"]
        assert out["interpretation"]["daily_score_does_not_imply_daily_turnover"] is True
        assert out["interpretation"]["prospective_evidence_does_not_grant_allocation_authority"] is True
        continuity = out["program_continuity"]["SEMICONDUCTOR_FORWARD"]
        assert continuity["first_frozen_signal_date"] == "2026-09-04"
        assert continuity["predecessor"]["elapsed_close_to_close_sessions"] == 4
        assert continuity["current_cohort"]["signal_date"] == "2026-09-10"
        assert continuity["overlapping_sessions_are_not_additive"] is True
        assert out["coverage"]["predecessor_forward_identities"]["P438_SEMICONDUCTOR_FORWARD_MTD_R1"] is True
        frozen = {
            "cohort_id": "SEMICONDUCTOR_SHARED_RIDGE:2026-09-11:fixed20",
            "program_id": "SEMICONDUCTOR_SHARED_RIDGE",
            "signal_date": "2026-09-11",
            "first_registered_at": "2026-09-12T00:00:00+00:00",
            "status": "RESOLVED",
            "resolution": {"ticker_book_net_return_bps": 895.5707,
                           "ticker_book_excess_vs_smh_bps": -18.3719},
        }
        projected = {
            "status": "DERIVED_FROM_FROZEN_RESOLVED_COHORT_NO_OUTCOME_BACKFILL",
            "ticker_minus_smh_net_bps": -8.3719,
            "ticker_minus_equal_weight_13_net_bps": -125.2211,
            "original_resolution_mutated": False,
            "alpha_or_promotion_authority": False,
        }
        ledger = {
            "schema": LEDGER_SCHEMA,
            "cohorts": [frozen],
            "summary": {"SEMICONDUCTOR_SHARED_RIDGE": {
                "registered_cohorts": 1, "resolved_cohorts": 1, "open_cohorts": 0,
                "mean_ticker_book_excess_vs_smh_bps": -18.3719,
            }},
            "matched_after_cost_projections": {frozen["cohort_id"]: projected},
        }
        original_frozen = json.dumps(frozen, sort_keys=True)
        state = _prospective_state(ledger, "SEMICONDUCTOR_SHARED_RIDGE")
        # The frozen one-cohort source cannot be promoted by a fabricated
        # summary count, even if a separate matched-cost projection exists.
        for bad in (20, "20", 20.0, True, -1):
            changed = {**ledger, "summary": {"SEMICONDUCTOR_SHARED_RIDGE": {
                **ledger["summary"]["SEMICONDUCTOR_SHARED_RIDGE"],
                "resolved_cohorts": bad,
                "minimum_resolved_for_promotion": 20,
            }}}
            try:
                _prospective_state(changed, "SEMICONDUCTOR_SHARED_RIDGE")
            except ValueError as exc:
                assert str(exc) == "PROSPECTIVE_COHORT_SUMMARY_COUNT_MISMATCH:SEMICONDUCTOR_SHARED_RIDGE"
            else:
                raise AssertionError("unverified summary claimed twenty resolved H20 cohorts")
        wrong_registered = {**ledger, "summary": {"SEMICONDUCTOR_SHARED_RIDGE": {
            **ledger["summary"]["SEMICONDUCTOR_SHARED_RIDGE"],
            "registered_cohorts": 2,
        }}}
        try:
            _prospective_state(wrong_registered, "SEMICONDUCTOR_SHARED_RIDGE")
        except ValueError as exc:
            assert str(exc) == "PROSPECTIVE_COHORT_SUMMARY_COUNT_MISMATCH:SEMICONDUCTOR_SHARED_RIDGE"
        else:
            raise AssertionError("unverified summary claimed extra registered cohorts")
        for status, wrong_field in (("OPEN", "open_cohorts"), ("LATE_REGISTRATION_REJECTED", "late_registration_rejections")):
            tampered = {**ledger, "cohorts": [{**frozen, "status": status}],
                        "summary": {"SEMICONDUCTOR_SHARED_RIDGE": {
                            "registered_cohorts": 1, "resolved_cohorts": 0,
                            "open_cohorts": 0, "late_registration_rejections": 0,
                            "minimum_resolved_for_promotion": 20}}}
            try:
                _prospective_state(tampered, "SEMICONDUCTOR_SHARED_RIDGE")
            except ValueError as exc:
                assert str(exc) == "PROSPECTIVE_COHORT_SUMMARY_COUNT_MISMATCH:SEMICONDUCTOR_SHARED_RIDGE"
            else:
                raise AssertionError(f"unverified {wrong_field} hid {status} source row")
        floor_spoof = {**ledger, "summary": {"SEMICONDUCTOR_SHARED_RIDGE": {
            **ledger["summary"]["SEMICONDUCTOR_SHARED_RIDGE"],
            "minimum_resolved_for_promotion": 1,
        }}}
        try:
            _prospective_state(floor_spoof, "SEMICONDUCTOR_SHARED_RIDGE")
        except ValueError as exc:
            assert str(exc) == "PROSPECTIVE_COHORT_PROMOTION_FLOOR_MISMATCH:SEMICONDUCTOR_SHARED_RIDGE"
        else:
            raise AssertionError("one resolved cohort lowered frozen full-promotion floor")
        assert state["forward_science_stages"]["full_promotion_sample_floor_reached"] is False
        assert state["mean_ticker_book_excess_vs_smh_bps"] == -18.3719
        assert state["mean_ticker_book_excess_vs_smh_net_bps"] == -8.3719
        assert state["mean_ticker_book_excess_vs_equal_weight_13_net_bps"] == -125.2211
        assert state["current_resolution"]["matched_after_cost"]["ticker_minus_smh_net_bps"] == -8.3719
        chain = _decision_chain([{"program_id": "SEMICONDUCTOR_SHARED_RIDGE", "prospective_evidence": state}])
        assert chain["realized_excess"]["semiconductor_mean_ticker_book_excess_vs_smh_bps"] == -18.3719
        assert chain["realized_excess"]["semiconductor_mean_ticker_book_excess_vs_smh_net_bps"] == -8.3719
        assert chain["realized_excess"]["semiconductor_mean_ticker_book_excess_vs_equal_weight_13_net_bps"] == -125.2211
        assert json.dumps(frozen, sort_keys=True) == original_frozen
        del ledger["matched_after_cost_projections"]
        absent = _prospective_state(ledger, "SEMICONDUCTOR_SHARED_RIDGE")
        assert absent["matched_cost_projection_status"] == "MATCHED_COST_PROJECTION_INCOMPLETE"
        assert absent["mean_ticker_book_excess_vs_smh_net_bps"] is None
        ledger["matched_after_cost_projections"] = {frozen["cohort_id"]: dict(projected, ticker_minus_smh_net_bps=True)}
        invalid = _prospective_state(ledger, "SEMICONDUCTOR_SHARED_RIDGE")
        assert invalid["matched_cost_projection_status"] == "MATCHED_COST_PROJECTION_INCOMPLETE"
        assert invalid["mean_ticker_book_excess_vs_smh_net_bps"] is None

        # Consume the independently accepted #2006 duplicate-native-adapter
        # identity guard in the selected #2012 composite without changing its
        # matched-book, source freshness, or economic projection semantics.
        duplicate_dir = root / "shadow-native"
        duplicate_dir.mkdir()
        original_adapter = root / "forward_program_adapter_0.json"
        duplicate_adapter = duplicate_dir / "duplicate.json"
        duplicate_adapter.write_bytes(original_adapter.read_bytes())
        assert _load_native_adapters(root)["SEMICONDUCTOR_SHARED_RIDGE"] == semi
        duplicate_adapter.write_text(json.dumps(dict(semi, signal_date="2026-10-23")))
        for original_payload, duplicate_payload in (
            (semi, dict(semi, signal_date="2026-10-23")),
            (dict(semi, signal_date="2026-10-23"), semi),
        ):
            original_adapter.write_text(json.dumps(original_payload))
            duplicate_adapter.write_text(json.dumps(duplicate_payload))
            for loader in (_load_native_adapters, build):
                try:
                    loader(root)
                except ValueError as exc:
                    assert str(exc) == "DUPLICATE_NATIVE_ADAPTER_PROGRAM_ID:SEMICONDUCTOR_SHARED_RIDGE"
                else:
                    raise AssertionError("conflicting native program identity was silently accepted")
        duplicate_adapter.unlink()
        original_adapter.write_text(json.dumps(semi))
        assert _load_native_adapters(root)["SEMICONDUCTOR_SHARED_RIDGE"] == semi

        # The canonical prospective ledger already rejects nested duplicate
        # adapter keys and nonfinite JSON constants. The scoreboard must make
        # the same source decision rather than silently using last-wins JSON.
        assert "signal" in semi
        for malformed, code in (
            (json.dumps(semi)[:-1] + ',"signal":{"positive_symbols":["FAKE"]}}',
             "FORWARD_ADAPTER_DUPLICATE_JSON_KEY"),
            (json.dumps(semi)[:-1] + ',"synthetic_nonfinite":NaN}',
             "FORWARD_ADAPTER_NONFINITE_JSON_CONSTANT"),
        ):
            original_adapter.write_text(malformed)
            try:
                _load_native_adapters(root)
            except RuntimeError as exc:
                assert str(exc) == code
            else:
                raise AssertionError("ambiguous native adapter JSON admitted")
        original_adapter.write_text(json.dumps(semi))
        # An unrelated JSON artifact must not poison recognized native inputs.
        unrelated = root / "unrelated-duplicate.json"
        unrelated.write_text('{"not_an_adapter":1,"not_an_adapter":2}')
        assert _load_native_adapters(root)["SEMICONDUCTOR_SHARED_RIDGE"] == semi
        # A first recognized schema overwritten by a later unrelated schema
        # must not silently bypass the canonical strict adapter parser.
        for malformed in (
            '{"schema":"foundry.forward_program_adapter.v1","schema":"unrelated"}',
            '{"schema":"unrelated","schema":"foundry.forward_program_adapter.v1"}',
        ):
            unrelated.write_text(malformed)
            try:
                _load_native_adapters(root)
            except RuntimeError as exc:
                assert str(exc) == "FORWARD_ADAPTER_DUPLICATE_JSON_KEY"
            else:
                raise AssertionError("duplicate top-level native schema bypassed strict parsing")
        # A nested schema lookalike is not a top-level native adapter.
        unrelated.write_text(
            '{"schema":"unrelated","nested":{"schema":"foundry.forward_program_adapter.v1","k":1,"k":2}}'
        )
        assert _load_native_adapters(root)["SEMICONDUCTOR_SHARED_RIDGE"] == semi
        unrelated.unlink()

    # Homebuilders legacy stock-net vs ITB-gross is not matched-after-cost alpha.
    homebuilders_cost_ledger = {
        "schema": LEDGER_SCHEMA,
        "cohorts": [{"cohort_id": "HB_COST", "program_id": "HOMEBUILDERS",
                     "status": "RESOLVED", "signal_date": "2026-09-10",
                     "first_registered_at": "2026-09-11T00:00:00+00:00",
                     "stock_round_trip_cost_bps": 25.0,
                     "resolution": {"observations": [{
                         "status": "RESOLVED", "net_return_bps": 100.0,
                         "itb_return_bps": 11.0361, "qqq_return_bps": 599.9839,
                         "excess_vs_itb_bps": 88.9639,
                         "excess_vs_qqq_bps": -499.9839}]}}],
        "summary": {"HOMEBUILDERS": {"resolved_cohorts": 1,
                                    "mean_excess_vs_itb_bps": 88.9639}},
        "homebuilders_cost_basis_projections": {
            "HB_COST": {"status": "DERIVED_MIXED_COST_ONLY_BENCHMARK_FEES_UNFROZEN",
                        "resolved_observations": 1,
                        "stock_round_trip_cost_bps": 25.0,
                        "stock_net_mean_bps": 100.0,
                        "itb_gross_mean_bps": 11.0361,
                        "qqq_gross_mean_bps": 599.9839,
                        "legacy_stock_net_minus_itb_gross_mean_bps": 88.9639,
                        "legacy_stock_net_minus_qqq_gross_mean_bps": -499.9839,
                        "matched_stock_net_minus_itb_net_mean_bps": None,
                        "original_resolution_mutated": False,
                        "alpha_or_promotion_authority": False}},
    }
    homebuilders_state = _prospective_state(homebuilders_cost_ledger, "HOMEBUILDERS")
    assert homebuilders_state["homebuilders_cost_basis_projection_status"] == "ALL_RESOLVED_COHORTS_MIXED_COST_LABELLED"
    assert homebuilders_state["mean_excess_vs_itb_bps"] == 88.9639
    assert homebuilders_state["mean_matched_after_cost_excess_vs_itb_bps"] is None
    assert homebuilders_state["homebuilders_funded_portfolio_nav_return_bps"] is None
    assert homebuilders_state["legacy_mean_excess_vs_itb_basis"] == "STOCK_NET_MINUS_ITB_GROSS_NOT_MATCHED_AFTER_COST"
    # False-green falsifiers: a status-only resolved cohort with zero rows,
    # a stale cost projection and a changed original row must all fail closed.
    empty_homebuilders = dict(homebuilders_cost_ledger)
    empty_homebuilders["cohorts"] = [{
        **homebuilders_cost_ledger["cohorts"][0], "resolution": {"observations": []}
    }]
    assert _prospective_state(empty_homebuilders, "HOMEBUILDERS")[
        "homebuilders_cost_basis_projection_status"] == "MIXED_COST_PROJECTION_INCOMPLETE"
    stale_homebuilders = dict(homebuilders_cost_ledger)
    stale_homebuilders["homebuilders_cost_basis_projections"] = {
        "HB_COST": {**homebuilders_cost_ledger["homebuilders_cost_basis_projections"]["HB_COST"],
                    "stock_round_trip_cost_bps": 50.0}}
    assert _prospective_state(stale_homebuilders, "HOMEBUILDERS")[
        "homebuilders_cost_basis_projection_status"] == "MIXED_COST_PROJECTION_INCOMPLETE"
    changed_homebuilders = dict(homebuilders_cost_ledger)
    changed_homebuilders["cohorts"] = [{
        **homebuilders_cost_ledger["cohorts"][0],
        "resolution": {"observations": [{
            **homebuilders_cost_ledger["cohorts"][0]["resolution"]["observations"][0],
            "excess_vs_itb_bps": 77.0}]}
    }]
    assert _prospective_state(changed_homebuilders, "HOMEBUILDERS")[
        "homebuilders_cost_basis_projection_status"] == "MIXED_COST_PROJECTION_INCOMPLETE"
    partial_homebuilders = dict(homebuilders_cost_ledger)
    partial_homebuilders["cohorts"] = [{
        **homebuilders_cost_ledger["cohorts"][0],
        "status": "PARTIALLY_RESOLVED",
        "resolution": {"observations": [
            dict(homebuilders_cost_ledger["cohorts"][0]["resolution"]["observations"][0]),
            {"status": "OPEN"}]},
    }]
    partial_homebuilders["summary"] = {"HOMEBUILDERS": {"resolved_cohorts": 0}}
    partial_state = _prospective_state(partial_homebuilders, "HOMEBUILDERS")
    assert partial_state["homebuilders_cost_basis_projection_status"] == "ALL_REPORTABLE_PARTIAL_COHORTS_MIXED_COST_LABELLED"

    # Cross-program freshness must not go green merely because all symbols
    # stopped on the same old day while another observed source has a newer
    # completed exchange session.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "forward_p249_p266_shadow_r1.json").write_text(json.dumps({
            "source_health": {
                "latest_scored_common_session": "2026-10-23",
                "common_session_lags_source_max": False,
                "lagging_symbols_vs_source_max": [],
            },
        }))
        ledger_path = root / "forward_prospective_cohort_ledger_r1.json"
        stale_ledger = {
            "schema": LEDGER_SCHEMA,
            "market_data_asof": "2026-10-25",
            "freshness": {
                "freshness_gap_visible": False,
                "lagging_symbols_by_program": {},
                "source_health_by_program": {
                    "SEMICONDUCTOR_SHARED_RIDGE": {
                        "source_max_date": "2026-10-12",
                        "all_symbols_share_latest_date": True,
                    },
                },
            },
            "cohorts": [],
            "summary": {},
        }
        ledger_path.write_text(json.dumps(stale_ledger))
        stale_result = build(root)
        assert stale_result["freshness"]["freshness_gap_visible"] is True
        assert stale_result["freshness"]["forward_source_lag_vs_observed_completed_session"]["SEMICONDUCTOR_SHARED_RIDGE"]["source_max_date"] == "2026-10-12"
        # The actual current ledger has only RESOLVED cohorts: its source
        # snapshots freeze at the original exit by design, not provider outage.
        stale_ledger["freshness"]["source_health_by_program"]["SEMICONDUCTOR_SHARED_RIDGE"]["lagging_symbols_vs_source_max"] = []
        stale_ledger["cohorts"] = [{
            "cohort_id": "FROZEN_H20", "program_id": "SEMICONDUCTOR_SHARED_RIDGE",
            "status": "RESOLVED", "resolution": {"exit_date": "2026-10-12"},
        }]
        ledger_path.write_text(json.dumps(stale_ledger))
        terminal_result = build(root)
        assert terminal_result["freshness"]["forward_source_lag_vs_observed_completed_session"] == {}
        assert terminal_result["freshness"]["freshness_gap_visible"] is False
        assert terminal_result["freshness"]["terminal_cohort_source_snapshots"]["SEMICONDUCTOR_SHARED_RIDGE"]["state"] == "FROZEN_TERMINAL_COHORT_SOURCE_HISTORY_NOT_ACTIVE_STALENESS"
        # A synchronized P249 tape can still be missing a completed exchange
        # session. Frozen terminal cohort snapshots must not mask that gap.
        p249_gap_path = root / "forward_p249_p266_shadow_r1.json"
        p249_gap = json.loads(p249_gap_path.read_text())
        p249_gap["source_health"]["unresolved_forward_gap"] = {
            "first_unresolved_session": "2026-10-23",
            "missing_held_symbols": [],
            "reason": "MISSING_EXCHANGE_SESSION_ALL_SYMBOLS",
        }
        p249_gap_path.write_text(json.dumps(p249_gap))
        independent_gap = build(root)["freshness"]
        assert independent_gap["freshness_gap_visible"] is True
        assert independent_gap["terminal_cohort_source_snapshots"]["SEMICONDUCTOR_SHARED_RIDGE"]["state"] == "FROZEN_TERMINAL_COHORT_SOURCE_HISTORY_NOT_ACTIVE_STALENESS"
        p249_gap["source_health"].pop("unresolved_forward_gap")
        p249_gap_path.write_text(json.dumps(p249_gap))
        # Missing exit identity must fail closed even with a RESOLVED label.
        stale_ledger["cohorts"][0]["resolution"] = {}
        ledger_path.write_text(json.dumps(stale_ledger))
        unbound_terminal = build(root)
        assert unbound_terminal["freshness"]["freshness_gap_visible"] is True
        stale_ledger["cohorts"][0]["status"] = "OPEN"
        ledger_path.write_text(json.dumps(stale_ledger))
        active_result = build(root)
        assert active_result["freshness"]["freshness_gap_visible"] is True
        assert active_result["freshness"]["forward_source_lag_vs_observed_completed_session"]["SEMICONDUCTOR_SHARED_RIDGE"]["source_max_date"] == "2026-10-12"
        stale_ledger["cohorts"] = []
        stale_ledger["freshness"]["source_health_by_program"]["SEMICONDUCTOR_SHARED_RIDGE"]["source_max_date"] = "2026-10-23"
        ledger_path.write_text(json.dumps(stale_ledger))
        current_result = build(root)
        assert current_result["freshness"]["forward_source_lag_vs_observed_completed_session"] == {}
        assert current_result["freshness"]["freshness_gap_visible"] is False
        stale_ledger["freshness"]["source_health_by_program"]["SEMICONDUCTOR_SHARED_RIDGE"]["source_max_date"] = "2026-10-23garbage"
        ledger_path.write_text(json.dumps(stale_ledger))
        malformed_source = build(root)["freshness"]
        assert malformed_source["forward_source_lag_vs_observed_completed_session"]["SEMICONDUCTOR_SHARED_RIDGE"]["state"] == "INVALID_SOURCE_DATE"
        assert malformed_source["freshness_gap_visible"] is True
        stale_ledger["freshness"]["source_health_by_program"]["SEMICONDUCTOR_SHARED_RIDGE"]["source_max_date"] = "2026-10-23"
        ledger_path.write_text(json.dumps(stale_ledger))
        p249_path = root / "forward_p249_p266_shadow_r1.json"
        p249 = json.loads(p249_path.read_text())
        p249["source_health"]["latest_scored_common_session"] = "2026-10-23T99:99:99Z"
        p249_path.write_text(json.dumps(p249))
        malformed_reference = build(root)["freshness"]
        assert malformed_reference["forward_source_reference_state"] == "INVALID_INDEPENDENT_COMPLETED_SESSION"
        assert malformed_reference["freshness_gap_visible"] is True
        p249["source_health"].pop("latest_scored_common_session")
        p249_path.write_text(json.dumps(p249))
        missing_reference = build(root)["freshness"]
        assert missing_reference["forward_source_reference_state"] == "NO_INDEPENDENT_COMPLETED_SESSION"
        assert missing_reference["freshness_gap_visible"] is True

    # The new P558/JAAA wealth ratios require explicit both-net source basis,
    # matched observation completeness and valid funded terminal NAVs.
    challenger = {
        "contract": {"entry_and_mark_to_market_exit_cost_bps_each": 25},
        "current_positions": {"challenger": {"KMLM": 0.5}},
        "forward": {
            "challenger_if_flattened_now": {"days": 1, "cumulative_return": -0.02054759529211936},
            "incumbent": {"cumulative_return": -0.0298141670103782},
            "matched_control_if_flattened_now": {"cumulative_return": -0.017146162108331087},
            "challenger_minus_incumbent_cumulative": 0.009266571718258843,
            "challenger_minus_matched_cumulative": -0.0034014331837882716,
            "challenger_observations": [{"date": "2026-10-23", "net_return": -0.01804759529211936, "core_return": -0.0298141670103782}],
            "matched_control_observations": [{"date": "2026-10-23", "net_return": -0.014646162108331087}],
            "comparison_cost_basis": {
                "challenger_minus_incumbent_cumulative":
                    "CHALLENGER_NET_IF_FLATTENED_NOW_MINUS_UNCHANGED_INCUMBENT_NET",
                "challenger_minus_matched_cumulative": "BOTH_NET_IF_FLATTENED_NOW",
                "legacy_pre_exit_spreads_not_used": True,
            },
        },
    }
    matched = _challenger(challenger, "P558", "KMLM")["scorecard"]
    assert matched["matched_cost_basis"] == "BOTH_NET_IF_FLATTENED_NOW"
    assert matched["challenger_absolute_net_if_flattened_now_bps"] == -205.48
    assert matched["incumbent_absolute_net_if_flattened_now_bps"] == -298.14
    assert matched["matched_control_absolute_net_if_flattened_now_bps"] == -171.46
    assert matched["challenger_vs_incumbent_relative_wealth_bps"] == 95.51
    assert matched["challenger_vs_matched_control_relative_wealth_bps"] == -34.61
    challenger["contract"]["entry_and_mark_to_market_exit_cost_bps_each"] = 30
    changed_fee = _challenger(challenger, "P558", "KMLM")["scorecard"]
    assert changed_fee["funded_nav_reconciliation"] == "FAIL_CLOSED"
    assert changed_fee["matched_cost_basis"] == "UNADMITTED_OR_INCOMPLETE"
    challenger["contract"]["entry_and_mark_to_market_exit_cost_bps_each"] = 25

    # Complete, finite rows with a mismatched funded terminal NAV are not
    # independent both-net evidence; a self-declared basis cannot rescue them.
    original_incumbent = challenger["forward"]["incumbent"]["cumulative_return"]
    challenger["forward"]["incumbent"]["cumulative_return"] += 0.001
    tampered = _challenger(challenger, "P558", "KMLM")["scorecard"]
    assert tampered["funded_nav_reconciliation"] == "FAIL_CLOSED"
    assert tampered["matched_cost_basis"] == "UNADMITTED_OR_INCOMPLETE"
    challenger["forward"]["incumbent"]["cumulative_return"] = original_incumbent

    challenger["forward"]["comparison_cost_basis"]["legacy_pre_exit_spreads_not_used"] = False
    held = _challenger(challenger, "P558", "KMLM")["scorecard"]
    assert held["matched_cost_basis"] == "UNADMITTED_OR_INCOMPLETE"
    assert held["challenger_vs_incumbent_relative_wealth_bps"] is None
    challenger["forward"]["comparison_cost_basis"]["legacy_pre_exit_spreads_not_used"] = True
    challenger["forward"]["matched_control_observations"] = []
    held = _challenger(challenger, "P558", "KMLM")["scorecard"]
    assert held["matched_cost_basis"] == "UNADMITTED_OR_INCOMPLETE"
    assert held["challenger_vs_matched_control_relative_wealth_bps"] is None
    challenger["forward"]["matched_control_observations"] = []
    challenger["forward"]["challenger_observations"] = []
    challenger["forward"]["challenger_if_flattened_now"]["days"] = 0
    zero_day = _challenger(challenger, "P558", "KMLM")["scorecard"]
    assert zero_day["matched_cost_basis"] == "UNADMITTED_OR_INCOMPLETE"
    assert zero_day["challenger_vs_incumbent_relative_wealth_bps"] is None

    # Explicit both-net labels must not survive invalid terminal NAV inputs,
    # even when source metadata and matched rows look complete.
    challenger["forward"]["challenger_if_flattened_now"]["days"] = 1
    challenger["forward"]["challenger_observations"] = [
        {"date": "2026-10-23", "net_return": -0.01804759529211936, "core_return": -0.0298141670103782}
    ]
    challenger["forward"]["matched_control_observations"] = [
        {"date": "2026-10-23", "net_return": -0.014646162108331087}
    ]
    for key, invalid_nav in (
        ("incumbent", None),
        ("incumbent", float("nan")),
        ("incumbent", float("inf")),
        ("incumbent", -1.0),
        ("incumbent", "0.02"),
        ("incumbent", True),
        ("incumbent", 10**400),
        ("matched_control_if_flattened_now", 1e307),
    ):
        original_nav = challenger["forward"][key]["cumulative_return"]
        challenger["forward"][key]["cumulative_return"] = invalid_nav
        rejected = _challenger(challenger, "P558", "KMLM")["scorecard"]
        assert rejected["matched_cost_basis"] == "UNADMITTED_OR_INCOMPLETE"
        assert rejected["challenger_vs_incumbent_relative_wealth_bps"] is None
        assert rejected["challenger_vs_matched_control_relative_wealth_bps"] is None
        assert rejected["incumbent_absolute_net_if_flattened_now_bps"] is None
        challenger["forward"][key]["cumulative_return"] = original_nav
    # Individually finite NAVs can still overflow their relative-wealth
    # ratio when the control wealth is extremely close to zero.
    challenger["forward"]["challenger_if_flattened_now"]["cumulative_return"] = 1e303
    challenger["forward"]["incumbent"]["cumulative_return"] = -1.0 + 1e-16
    challenger["forward"]["challenger_observations"][0]["net_return"] = 1e303
    challenger["forward"]["challenger_observations"][0]["core_return"] = -1.0 + 1e-16
    overflow = _challenger(challenger, "P558", "KMLM")["scorecard"]
    assert overflow["funded_nav_reconciliation"] == "PASS_THREE_BOOKS"
    assert overflow["matched_cost_basis"] == "UNADMITTED_OR_INCOMPLETE"
    assert overflow["challenger_vs_incumbent_relative_wealth_bps"] is None
    challenger["forward"]["challenger_if_flattened_now"]["cumulative_return"] = -0.02054759529211936
    challenger["forward"]["incumbent"]["cumulative_return"] = -0.0298141670103782
    challenger["forward"]["challenger_observations"][0]["net_return"] = -0.01804759529211936
    challenger["forward"]["challenger_observations"][0]["core_return"] = -0.0298141670103782

    original_challenger_nav = challenger["forward"]["challenger_if_flattened_now"]["cumulative_return"]
    challenger["forward"]["challenger_if_flattened_now"]["cumulative_return"] = float("nan")
    rejected = _challenger(challenger, "P558", "KMLM")["scorecard"]
    assert rejected["matched_cost_basis"] == "UNADMITTED_OR_INCOMPLETE"
    assert rejected["challenger_cumulative_bps"] is None
    challenger["forward"]["challenger_if_flattened_now"]["cumulative_return"] = original_challenger_nav

    # Generic producer artifacts can be duplicated by nested artifact download.
    # Byte-identical transport copies are harmless, but conflicting copies
    # must not silently select a different frozen input by filesystem order.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for name in (
            "forward_prospective_cohort_ledger_r1.json",
            "forward_p249_p266_shadow_r1.json",
        ):
            first = root / name
            duplicate_dir = root / "nested-transport-copy"
            duplicate_dir.mkdir(exist_ok=True)
            second = duplicate_dir / name
            first.write_text(json.dumps({"source_health": {"source_max_date": "2026-10-23"}}))
            second.write_bytes(first.read_bytes())
            assert _load(root, name) == {"source_health": {"source_max_date": "2026-10-23"}}
            second.write_text(json.dumps({"source_health": {"source_max_date": "2026-10-12"}}))
            for first_value, second_value in (
                ("2026-10-23", "2026-10-12"),
                ("2026-10-12", "2026-10-23"),
            ):
                first.write_text(json.dumps({"source_health": {"source_max_date": first_value}}))
                second.write_text(json.dumps({"source_health": {"source_max_date": second_value}}))
                for loader in (
                    lambda: _load(root, name),
                    lambda: build(root),
                ):
                    try:
                        loader()
                    except ValueError as exc:
                        assert str(exc) == f"CONFLICTING_SCOREBOARD_INPUT:{name}"
                    else:
                        raise AssertionError("conflicting canonical input was silently accepted")
            first.unlink()
            second.unlink()
        # New exact canonical producer falsifier: the old default json.loads
        # silently took the last duplicate freshness/score key. Unrelated
        # artifact files remain ignored; only these named producer inputs fail.
        for canonical in (
            "p46_forward_observation_v2.json",
            "forward_p249_p266_shadow_r1.json",
            "forward_p558_current_core_shadow_r1.json",
            "forward_senior_clo_current_core_shadow_r1.json",
            "p438_semiconductor_forward_mtd_r1.json",
            "forward_prospective_cohort_ledger_r1.json",
        ):
            target = root / canonical
            for ambiguous in (
                '{"source_health":{"source_max_date":"2026-10-23","source_max_date":"2026-10-12"}}',
                '{"source_health":{"source_max_date":"2026-10-23"},"source_health":{"source_max_date":"2026-10-12"}}',
                '{"source_health":{"source_max_date":"2026-10-23"},"score":NaN}',
            ):
                target.write_text(ambiguous)
                try:
                    _load(root, canonical)
                except ValueError:
                    pass
                else:
                    raise AssertionError("ambiguous canonical scoreboard JSON was silently accepted")
            target.unlink()
        invalid = root / "forward_p249_p266_shadow_r1.json"
        invalid.write_text("[]")
        try:
            _load(root, invalid.name)
        except ValueError as exc:
            assert str(exc) == f"INVALID_SCOREBOARD_INPUT:{invalid.name}"
        else:
            raise AssertionError("non-object canonical input was silently accepted")

    # The actual report job stages prior-current historical bytes alongside
    # newly resolved prospective-current bytes. They are intentionally
    # different; select the fresh producer without weakening same-source
    # duplicate-content fail-close.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        historical = root / "prior-current"
        current = root / "prospective-current"
        historical.mkdir()
        current.mkdir()
        name = "forward_prospective_cohort_ledger_r1.json"
        (historical / name).write_text(json.dumps({"source": "prior"}))
        fresh = current / name
        fresh.write_text(json.dumps({"source": "fresh"}))
        assert _load_prospective_ledger(root) == {"source": "fresh"}
        # The prospective producer's own strict prior parser rejects these
        # ambiguous ledger bytes. The scoreboard must reject them too.
        for malformed, code in (
            ('{"source":"fresh","cohorts":[],"cohorts":[{"cohort_id":"FORGED"}]}',
             "FORWARD_ADAPTER_DUPLICATE_JSON_KEY"),
            ('{"source":"fresh","cohorts":[{"first_registered_at":NaN}]}',
             "FORWARD_ADAPTER_NONFINITE_JSON_CONSTANT"),
        ):
            fresh.write_text(malformed)
            try:
                _load_prospective_ledger(root)
            except RuntimeError as exc:
                assert str(exc) == code
            else:
                raise AssertionError("ambiguous prospective ledger JSON admitted")
        fresh.write_text(json.dumps({"source": "fresh"}))
        duplicate = current / "nested-copy"
        duplicate.mkdir()
        (duplicate / name).write_text(json.dumps({"source": "different-current"}))
        try:
            _load_prospective_ledger(root)
        except ValueError as exc:
            assert str(exc) == f"CONFLICTING_SCOREBOARD_INPUT:{name}"
        else:
            raise AssertionError("conflicting current-producer copy was admitted")
        (duplicate / name).unlink()
        fresh.unlink()
        try:
            _load_prospective_ledger(root)
        except ValueError as exc:
            assert str(exc) == "CURRENT_PROSPECTIVE_LEDGER_NOT_MATERIALIZED"
        else:
            raise AssertionError("prior-current history substituted for missing fresh ledger")

    print("FORWARD_MARKET_SCOREBOARD_SELF_TEST=PASS")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-root", default="artifacts")
    ap.add_argument("--output", default="artifacts/forward_market_scoreboard_r1.json")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    out = build(Path(args.input_root))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({"schema": out["schema"], "scored_now": out["coverage"]["scored_now"], "native_result_gaps": out["coverage"]["native_result_gaps"]}, sort_keys=True))


if __name__ == "__main__":
    main()
