from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "research.forward_market_scoreboard_r1"
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


def build(root: Path) -> dict[str, Any]:
    p46 = _p46(_load(root, "p46_forward_observation_v2.json"))
    p249 = _p249(_load(root, "forward_p249_p266_shadow_r1.json"))
    p558 = _challenger(_load(root, "forward_p558_current_core_shadow_r1.json"), "P558", "KMLM")
    clo = _challenger(_load(root, "forward_senior_clo_current_core_shadow_r1.json"), "SENIOR_CLO", "JAAA")
    lanes = [p46, p249, p558, clo]

    missing = [
        {
            "program_id": p,
            "status": "ADAPTER_NOT_CONNECTED_TO_THIS_REPORT",
            "validation_grade": "NO_COMMON_SCORE",
            "decision_use": "Preserve native observer output; do not infer a common score until its registered adapter is wired.",
        }
        for p in EXPECTED_PRIVATE_ADAPTERS
    ]

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

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Daily/on-demand forward validation and market-decision reporting across frozen research survivors.",
        "lanes": lanes + missing,
        "market_decision_context": actionable_context,
        "coverage": {
            "scored_now": [x.get("program_id") for x in lanes],
            "adapter_gaps": list(EXPECTED_PRIVATE_ADAPTERS),
        },
        "interpretation": {
            "weight_is_not_forecast": True,
            "positive_model_score_is_not_position_size": True,
            "forward_score_requires_matched_benchmark_or_control": True,
            "small_samples_are_not_promotion_evidence": True,
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
        out = build(root)
        assert out["schema"] == SCHEMA
        assert out["lanes"][0]["validation_grade"] == "SHAKEDOWN_ONLY"
        assert out["lanes"][1]["scorecard"]["p266_increment_cumulative_bps"] == -10.0
        assert "SEMICONDUCTOR_SHARED_RIDGE" in out["coverage"]["adapter_gaps"]
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
    print(json.dumps({"schema": out["schema"], "scored_now": out["coverage"]["scored_now"], "adapter_gaps": out["coverage"]["adapter_gaps"]}, sort_keys=True))


if __name__ == "__main__":
    main()
