from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "research.forward_market_scoreboard_r1"
ADAPTER_SCHEMA = "foundry.forward_program_adapter.v1"
LEDGER_SCHEMA = "research.forward_prospective_cohort_ledger_r1"
EXPECTED_PRIVATE_ADAPTERS = (
    "SEMICONDUCTOR_SHARED_RIDGE",
    "HOMEBUILDERS",
    "GENERALIZED_LARGECAP_RIDGE",
)


def _load(root: Path, name: str) -> dict[str, Any] | None:
    matches = list(root.rglob(name))
    if not matches:
        return None
    return json.loads(matches[0].read_text())


def _load_native_adapters(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in root.rglob("*.json"):
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if payload.get("schema") != ADAPTER_SCHEMA:
            continue
        program_id = str(payload.get("program_id") or "")
        if program_id in EXPECTED_PRIVATE_ADAPTERS:
            out[program_id] = payload
    return out


def _bp(x: float | int | None) -> float | None:
    return None if x is None else round(float(x) * 10000.0, 2)


def _positive_session_stats(values: list[float]) -> dict[str, Any]:
    observed = len(values)
    positive = sum(1 for value in values if float(value) > 0.0)
    return {
        "observed_sessions": observed,
        "positive_sessions": positive,
        "hit_rate": None if observed == 0 else round(positive / observed, 6),
    }


def _challenger_session_stats(fwd: dict[str, Any]) -> dict[str, Any]:
    challenger = {
        str(row.get("date")): row
        for row in (fwd.get("challenger_observations") or [])
        if row.get("date")
    }
    incumbent_excess = [
        float(row.get("net_return", 0.0)) - float(row.get("core_return", 0.0))
        for row in challenger.values()
    ]
    matched = {
        str(row.get("date")): row
        for row in (fwd.get("matched_control_observations") or [])
        if row.get("date")
    }
    matched_excess = [
        float(row.get("net_return", 0.0)) - float(matched[day].get("net_return", 0.0))
        for day, row in challenger.items()
        if day in matched
    ]
    return {
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
    credit = bool(d.get("scientific_forward_credit_authorized", False))
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
    return {
        "program_id": "P249_P266",
        "kind": "portfolio_construction_plus_industry_momentum_satellite",
        "signal": {
            "p249_core_weights": state.get("p249_core", {}),
            "p266_industry_weights": state.get("p266", {}),
        },
        "timing": {
            "decision_cadence": "frozen monthly portfolio decision",
            "entry_rule": "rebalance the research book at the declared portfolio decision boundary, not every daily score run",
            "holding_rule": "keep frozen weights through the decision period; daily closes update forward PnL and excess only",
        },
        "paper_action": state.get("p249_plus_p266", {}),
        "action_text": f"Frozen combined portfolio: {_weights_text(state.get('p249_plus_p266', {}), 10)}.",
        "forward_days": days,
        "scorecard": {
            "p249_core_net_cumulative_bps": _bp(core.get("cumulative_return")),
            "p249_plus_p266_net_cumulative_bps": _bp(combo.get("cumulative_return")),
            "p266_increment_cumulative_bps": _bp(fwd.get("satellite_increment_cumulative")),
            "p266_increment_observed_sessions": increment_stats["observed_sessions"],
            "p266_increment_positive_sessions": increment_stats["positive_sessions"],
            "p266_increment_session_hit_rate": increment_stats["hit_rate"],
            "p249_core_annualized_vol": core.get("annualized_vol"),
            "p249_plus_p266_annualized_vol": combo.get("annualized_vol"),
        },
        "validation_grade": _grade(days),
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
            "challenger_cumulative_bps": _bp(metrics.get("cumulative_return")),
            "excess_vs_incumbent_bps": _bp(fwd.get("challenger_minus_incumbent_cumulative")),
            "excess_vs_matched_cash_control_bps": _bp(fwd.get("challenger_minus_matched_cumulative")),
            "vs_incumbent_observed_sessions": session_stats["vs_incumbent"]["observed_sessions"],
            "vs_incumbent_positive_sessions": session_stats["vs_incumbent"]["positive_sessions"],
            "vs_incumbent_session_hit_rate": session_stats["vs_incumbent"]["hit_rate"],
            "vs_matched_cash_control_observed_sessions": session_stats["vs_matched_cash_control"]["observed_sessions"],
            "vs_matched_cash_control_positive_sessions": session_stats["vs_matched_cash_control"]["positive_sessions"],
            "vs_matched_cash_control_session_hit_rate": session_stats["vs_matched_cash_control"]["hit_rate"],
            "max_drawdown": metrics.get("max_drawdown"),
            "annualized_vol": metrics.get("annualized_vol"),
        },
        "validation_grade": _grade(days),
        "decision_use": (
            f"Tests whether allocating half the incumbent portfolio to {alt} improves capital efficiency and diversification. "
            "A market decision requires positive excess versus both the unchanged incumbent and matched BIL control with enough forward observations."
        ),
        "boundaries": x.get("boundaries", {}),
    }



def _prospective_state(ledger: dict[str, Any] | None, program_id: str) -> dict[str, Any]:
    if ledger is None:
        return {"ledger_status": "NOT_SUPPLIED", "program_id": program_id}
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise RuntimeError(f"unexpected prospective ledger schema {ledger.get('schema')}")
    rows = [c for c in (ledger.get("cohorts") or []) if c.get("program_id") == program_id]
    summary = dict((ledger.get("summary") or {}).get(program_id) or {})
    current = max(
        rows,
        key=lambda c: (str(c.get("signal_date") or ""), str(c.get("first_registered_at") or "")),
        default=None,
    )
    out = {
        "ledger_status": "PRESENT",
        "program_id": program_id,
        "market_data_asof": ledger.get("market_data_asof"),
        "registered_cohorts": int(summary.get("registered_cohorts", len(rows)) or 0),
        "resolved_cohorts": int(summary.get("resolved_cohorts", 0) or 0),
        "open_cohorts": int(summary.get("open_cohorts", 0) or 0),
        "late_registration_rejections": int(summary.get("late_registration_rejections", 0) or 0),
        "minimum_resolved_for_promotion": summary.get("minimum_resolved_for_promotion"),
        "promotion_authority": False,
    }
    for key in (
        "resolved_observations",
        "positive_hit_rate",
        "mean_excess_vs_itb_bps",
        "mean_ticker_book_excess_vs_smh_bps",
        "mean_ticker_positive_hit_rate",
    ):
        if key in summary:
            out[key] = summary.get(key)
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
        if compact:
            out["current_resolution"] = compact
    return out


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
            "homebuilders_mean_excess_vs_itb_bps": (hb.get("prospective_evidence") or {}).get("mean_excess_vs_itb_bps"),
        },
        "resulting_market_decision_rule": (
            "Use P249/P266 as the frozen base research portfolio; treat P46 as regime context; add only native prospectively "
            "authorized cohorts such as Semiconductor three-book cohorts; use Homebuilders and generalized large-cap transport "
            "as decision evidence until a frozen sizing book exists; do not promote KMLM/JAAA substitutions until excess evidence is sufficient."
        ),
    }


def build(root: Path) -> dict[str, Any]:
    ledger = _load(root, "forward_prospective_cohort_ledger_r1.json")
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
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Daily/on-demand forward validation and market-decision reporting across frozen research survivors.",
        "lanes": lanes,
        "market_decision_context": actionable_context,
        "decision_chain": _decision_chain(lanes),
        "coverage": {
            "scored_now": [x.get("program_id") for x in lanes if x.get("signal")],
            "adapter_contracts_ready": list(EXPECTED_PRIVATE_ADAPTERS),
            "native_result_gaps": missing,
            "prospective_ledger": {
                "present": ledger is not None,
                "market_data_asof": None if ledger is None else ledger.get("market_data_asof"),
                "programs": [] if ledger is None else sorted((ledger.get("summary") or {}).keys()),
            },
        },
        "interpretation": {
            "weight_is_not_forecast": True,
            "positive_model_score_is_not_position_size": True,
            "forward_score_requires_matched_benchmark_or_control": True,
            "small_samples_are_not_promotion_evidence": True,
            "daily_score_does_not_imply_daily_turnover": True,
            "prospective_evidence_does_not_grant_allocation_authority": True,
            "broker_or_live_authority": False,
        },
    }


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "p46_forward_observation_v2.json").write_text(json.dumps({
            "decision": {"selected": ["DBC", "QQQ"], "scores": {"DBC": 0.85}, "target_weights": {"DBC": 0.5, "QQQ": 0.5}, "scientific_forward_credit_authorized": False},
            "operational_shadow": {"anchor_date": "2026-09-09", "latest_date": "2026-09-09"},
        }))
        (root / "forward_p249_p266_shadow_r1.json").write_text(json.dumps({
            "current_state": {"p249_core": {"SOXX": 0.4}, "p266": {"XBI": 1.0}, "p249_plus_p266": {"SOXX": 0.3, "XBI": 0.1}},
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
            "cohorts": [
                {"cohort_id": "HOMEBUILDERS:2026-09-10:test", "program_id": "HOMEBUILDERS", "signal_date": "2026-09-10", "first_registered_at": "2026-09-11T00:00:00+00:00", "status": "OPEN", "resolution": {"entry_date": "2026-09-11", "sessions_completed": 1}},
                {"cohort_id": "SEMICONDUCTOR_SHARED_RIDGE:2026-09-10:test", "program_id": "SEMICONDUCTOR_SHARED_RIDGE", "signal_date": "2026-09-10", "first_registered_at": "2026-09-11T00:00:00+00:00", "status": "AWAITING_ENTRY_SESSION", "resolution": None},
            ],
            "summary": {
                "HOMEBUILDERS": {"registered_cohorts": 1, "resolved_cohorts": 0, "open_cohorts": 1, "late_registration_rejections": 0, "minimum_resolved_for_promotion": None, "resolved_observations": 0, "mean_excess_vs_itb_bps": None},
                "SEMICONDUCTOR_SHARED_RIDGE": {"registered_cohorts": 1, "resolved_cohorts": 0, "open_cohorts": 1, "late_registration_rejections": 0, "minimum_resolved_for_promotion": 20, "mean_ticker_book_excess_vs_smh_bps": None},
            },
        }))
        out = build(root)
        assert out["schema"] == SCHEMA
        assert out["lanes"][0]["validation_grade"] == "SHAKEDOWN_ONLY"
        assert out["lanes"][1]["scorecard"]["p266_increment_cumulative_bps"] == -10.0
        assert out["lanes"][1]["scorecard"]["p266_increment_observed_sessions"] == 0
        stats = _challenger_session_stats({
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
        assert out["coverage"]["native_result_gaps"] == []
        assert out["decision_chain"]["sectors"]["homebuilders"]["horizons"] == {"CCS": 5}
        native_by_id = {x["program_id"]: x for x in out["lanes"]}
        assert native_by_id["HOMEBUILDERS"]["evidence_grade"] == "PROSPECTIVE_OPEN"
        assert native_by_id["SEMICONDUCTOR_SHARED_RIDGE"]["evidence_grade"] == "PROSPECTIVE_AWAITING_ENTRY_SESSION"
        assert native_by_id["SEMICONDUCTOR_SHARED_RIDGE"]["validation_grade"] == "PROSPECTIVE_SIGNAL_READY"
        assert out["coverage"]["prospective_ledger"]["present"] is True
        assert out["interpretation"]["daily_score_does_not_imply_daily_turnover"] is True
        assert out["interpretation"]["prospective_evidence_does_not_grant_allocation_authority"] is True
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
