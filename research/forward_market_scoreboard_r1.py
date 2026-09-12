from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "research.forward_market_scoreboard_r1"
ADAPTER_SCHEMA = "foundry.forward_program_adapter.v1"
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


def _native_lane(x: dict[str, Any]) -> dict[str, Any]:
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
            },
            "homebuilders": {
                "admitted": (hb.get("signal") or {}).get("admitted_symbols", []),
                "horizons": (hb.get("signal") or {}).get("duration_horizon_sessions_by_symbol", {}),
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
        },
        "resulting_market_decision_rule": (
            "Use P249/P266 as the frozen base research portfolio; treat P46 as regime context; add only native prospectively "
            "authorized cohorts such as Semiconductor three-book cohorts; use Homebuilders and generalized large-cap transport "
            "as decision evidence until a frozen sizing book exists; do not promote KMLM/JAAA substitutions until excess evidence is sufficient."
        ),
    }


def build(root: Path) -> dict[str, Any]:
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
            lanes.append(_native_lane(payload))
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
        },
        "interpretation": {
            "weight_is_not_forecast": True,
            "positive_model_score_is_not_position_size": True,
            "forward_score_requires_matched_benchmark_or_control": True,
            "small_samples_are_not_promotion_evidence": True,
            "daily_score_does_not_imply_daily_turnover": True,
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
        out = build(root)
        assert out["schema"] == SCHEMA
        assert out["lanes"][0]["validation_grade"] == "SHAKEDOWN_ONLY"
        assert out["lanes"][1]["scorecard"]["p266_increment_cumulative_bps"] == -10.0
        assert out["coverage"]["native_result_gaps"] == []
        assert out["decision_chain"]["sectors"]["homebuilders"]["horizons"] == {"CCS": 5}
        assert out["interpretation"]["daily_score_does_not_imply_daily_turnover"] is True
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
