from __future__ import annotations

"""Governed deterministic paper allocator for the common forward-model tape.

This is deliberately not a learned allocator and grants no broker/live authority.
It converts already-authoritative native model signals into one auditable paper/manual
portfolio expression so a learned allocator has a concrete baseline to beat.

Policy authority: XoticHaze/CommandCenter#770.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "research.forward_deterministic_allocator_r1"
POLICY_ID = "CC770_DETERMINISTIC_ALLOCATOR_V0"
CORE_BUDGET = 0.80
TACTICAL_BUDGET = 0.15
CASH_FLOOR = 0.05
GROSS_CAP = 1.00
SECTOR_CAP = 0.35
SINGLE_NAME_CAP = 0.05
NEW_COHORT_CAP = 0.05
NON_CORE_FAMILY_CAP = 0.10
EPS = 1e-9

SEMICONDUCTOR_ASSETS = {"SOXX", "XSD", "SMH"}


def _lane(scoreboard: dict[str, Any], program_id: str) -> dict[str, Any] | None:
    return next((x for x in scoreboard.get("lanes", []) if x.get("program_id") == program_id), None)


def _normalized(weights: dict[str, Any]) -> dict[str, float]:
    out = {str(k): max(0.0, float(v)) for k, v in weights.items() if float(v) > 0}
    total = sum(out.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in out.items()}


def _round_weights(weights: dict[str, float]) -> dict[str, float]:
    return {k: round(v, 10) for k, v in sorted(weights.items()) if v > EPS}


def _sector_exposure(weights: dict[str, float]) -> dict[str, float]:
    return {
        "semiconductor": sum(weights.get(x, 0.0) for x in SEMICONDUCTOR_ASSETS),
        "biotechnology": weights.get("XBI", 0.0),
        "pharmaceuticals": weights.get("XPH", 0.0),
        "software": weights.get("IGV", 0.0),
        "commodities": weights.get("DBC", 0.0),
    }


def _prior_targets(prior: dict[str, Any] | None) -> dict[str, float]:
    if not prior:
        return {}
    return {str(k): float(v) for k, v in (prior.get("final_target_weights") or {}).items()}


def _delta_actions(targets: dict[str, float], prior: dict[str, float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in sorted(set(targets) | set(prior)):
        target = float(targets.get(symbol, 0.0))
        before = float(prior.get(symbol, 0.0))
        delta = target - before
        if abs(delta) <= EPS:
            action = "HOLD" if target > EPS else "NO_ACTION"
        elif delta > 0:
            action = "ADD"
        elif target <= EPS:
            action = "EXIT"
        else:
            action = "REDUCE"
        rows.append({
            "symbol": symbol,
            "action": action,
            "prior_weight": round(before, 10),
            "target_weight": round(target, 10),
            "delta_weight": round(delta, 10),
        })
    return rows


def build(scoreboard: dict[str, Any], prior: dict[str, Any] | None = None) -> dict[str, Any]:
    p249 = _lane(scoreboard, "P249_P266") or {}
    base = _normalized(p249.get("paper_action") or {})
    if not base:
        raise RuntimeError("P249_P266 frozen core weights are required")

    final: dict[str, float] = {symbol: weight * CORE_BUDGET for symbol, weight in base.items()}
    constraints: list[dict[str, Any]] = [{
        "rule": "strategic_core_budget",
        "value": CORE_BUDGET,
        "result": "P249_P266 scaled pro-rata to 80% NAV",
    }]
    sleeve_actions: list[dict[str, Any]] = [{
        "sleeve": "P249_P266_CORE",
        "action": "HOLD",
        "target_weight": CORE_BUDGET,
        "reason": "frozen strategic core; daily score refresh is not a rebalance signal",
    }]

    tactical_used = 0.0

    # Semiconductor: choose the breadth-sized industry expression as the unified
    # baseline. The ticker-book expression remains a competing experiment and is
    # intentionally not stacked on top.
    semi = _lane(scoreboard, "SEMICONDUCTOR_SHARED_RIDGE") or {}
    semi_signal = semi.get("signal") or {}
    semi_grade = str(semi.get("validation_grade") or "")
    breadth = semi_signal.get("positive_breadth")
    semi_ready = semi_grade == "PROSPECTIVE_SIGNAL_READY" and isinstance(breadth, (int, float))
    if semi_ready:
        raw = min(NEW_COHORT_CAP * max(0.0, min(1.0, float(breadth))), NON_CORE_FAMILY_CAP)
        existing_sector = _sector_exposure(final)["semiconductor"]
        sector_room = max(0.0, SECTOR_CAP - existing_sector)
        tactical_room = max(0.0, TACTICAL_BUDGET - tactical_used)
        size = min(raw, sector_room, tactical_room, NEW_COHORT_CAP)
        if size > EPS:
            final["SMH"] = final.get("SMH", 0.0) + size
            tactical_used += size
            sleeve_actions.append({
                "sleeve": "SEMICONDUCTOR_SHARED_RIDGE_INDUSTRY_BOOK",
                "action": "ADD",
                "instrument": "SMH",
                "target_new_cohort_weight": round(size, 10),
                "native_horizon": "+1 session execution / fixed20 hold",
                "reason": f"breadth-sized paper expression: 5% * {float(breadth):.4f}",
            })
        else:
            sleeve_actions.append({
                "sleeve": "SEMICONDUCTOR_SHARED_RIDGE_INDUSTRY_BOOK",
                "action": "WAIT",
                "reason": "native signal ready but aggregate tactical/sector caps leave no room",
            })
        constraints.append({
            "rule": "semiconductor_sector_cap",
            "cap": SECTOR_CAP,
            "pre_overlay_exposure": round(existing_sector, 10),
            "raw_overlay": round(raw, 10),
            "admitted_overlay": round(size, 10),
        })
    else:
        sleeve_actions.append({
            "sleeve": "SEMICONDUCTOR_SHARED_RIDGE_INDUSTRY_BOOK",
            "action": "WAIT",
            "reason": "no current prospectively eligible native semiconductor result",
        })

    # Homebuilders: deterministic equal-weight family sizing is the temporary
    # portfolio-expression rule; the native model still owns admission and duration.
    hb = _lane(scoreboard, "HOMEBUILDERS") or {}
    hb_signal = hb.get("signal") or {}
    admitted = [str(x) for x in (hb_signal.get("admitted_symbols") or [])]
    horizons = hb_signal.get("duration_horizon_sessions_by_symbol") or {}
    if admitted:
        tactical_room = max(0.0, TACTICAL_BUDGET - tactical_used)
        family_size = min(0.05, NON_CORE_FAMILY_CAP, tactical_room)
        per_name = min(SINGLE_NAME_CAP, family_size / len(admitted)) if admitted else 0.0
        admitted_family = per_name * len(admitted)
        for symbol in admitted:
            final[symbol] = final.get(symbol, 0.0) + per_name
        tactical_used += admitted_family
        sleeve_actions.append({
            "sleeve": "HOMEBUILDERS",
            "action": "ADD" if admitted_family > EPS else "WAIT",
            "symbols": admitted,
            "family_weight": round(admitted_family, 10),
            "per_name_weight": round(per_name, 10),
            "native_horizons_sessions": {s: horizons.get(s) for s in admitted},
            "reason": "temporary deterministic equal-weight sizing; native model retains admission and 5/60 duration authority",
        })
    else:
        sleeve_actions.append({
            "sleeve": "HOMEBUILDERS",
            "action": "WAIT",
            "reason": "no currently admitted native homebuilder opportunity",
        })

    # Explicit non-authorities.
    large = _lane(scoreboard, "GENERALIZED_LARGECAP_RIDGE") or {}
    sleeve_actions.append({
        "sleeve": "GENERALIZED_LARGECAP_RIDGE",
        "action": "NO_ACTION",
        "target_weight": 0.0,
        "positive_corroboration": (large.get("signal") or {}).get("positive_symbols", []),
        "reason": "corroboration-only; no standalone sizing authority",
    })
    sleeve_actions.append({
        "sleeve": "P46",
        "action": "NO_ACTION",
        "target_weight": 0.0,
        "reason": "context-only while prospective scientific credit remains shakedown",
    })
    sleeve_actions.append({
        "sleeve": "P558_KMLM_SUBSTITUTION",
        "action": "NO_ACTION",
        "target_weight": 0.0,
        "reason": "challenger has not earned substitution authority versus incumbent and BIL control",
    })
    sleeve_actions.append({
        "sleeve": "SENIOR_CLO_JAAA_SUBSTITUTION",
        "action": "NO_ACTION",
        "target_weight": 0.0,
        "reason": "challenger has not earned substitution authority versus incumbent and BIL control",
    })

    invested = sum(final.values())
    if invested > GROSS_CAP + EPS:
        raise RuntimeError(f"gross cap violated before cash: {invested}")
    cash = GROSS_CAP - invested
    if cash + EPS < CASH_FLOOR:
        raise RuntimeError(f"cash floor violated: {cash}")
    final["CASH"] = cash

    sectors = _sector_exposure(final)
    if sectors["semiconductor"] > SECTOR_CAP + EPS:
        raise RuntimeError("semiconductor sector cap violated")
    if tactical_used > TACTICAL_BUDGET + EPS:
        raise RuntimeError("tactical budget violated")
    if abs(sum(final.values()) - 1.0) > 1e-8:
        raise RuntimeError("final weights do not sum to 100%")

    prior_targets = _prior_targets(prior)
    result = {
        "schema": SCHEMA,
        "policy_id": POLICY_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": "paper_manual_portfolio_expression_only",
        "source_scoreboard_schema": scoreboard.get("schema"),
        "source_scoreboard_generated_at": scoreboard.get("generated_at"),
        "budgets": {
            "strategic_core": CORE_BUDGET,
            "tactical_models": TACTICAL_BUDGET,
            "cash_floor": CASH_FLOOR,
            "gross_cap": GROSS_CAP,
            "sector_cap": SECTOR_CAP,
            "single_name_cap": SINGLE_NAME_CAP,
            "new_tactical_cohort_cap": NEW_COHORT_CAP,
            "non_core_family_cap": NON_CORE_FAMILY_CAP,
        },
        "sleeve_actions": sleeve_actions,
        "constraints_applied": constraints,
        "tactical_used": round(tactical_used, 10),
        "unused_tactical_budget": round(TACTICAL_BUDGET - tactical_used, 10),
        "sector_exposure": _round_weights(sectors),
        "final_target_weights": _round_weights(final),
        "cash_weight": round(cash, 10),
        "position_actions_vs_prior_allocator_target": _delta_actions(final, prior_targets),
        "prior_allocator_target_available": bool(prior_targets),
        "learned_allocator_role": "shadow_challenger_must_beat_this_baseline_after_costs_and_opportunity_cost",
        "controls_for_learned_allocator": [
            POLICY_ID,
            "equal_supported",
            "sticky_equal",
            "P249_P266_core_only",
            "cash_or_BIL_opportunity_cost",
        ],
        "boundaries": {
            "research_paper_only": True,
            "broker_action": False,
            "live_trading_change": False,
            "native_model_science_mutated": False,
            "prediction_magnitude_used_as_unbounded_size": False,
        },
    }
    return result


def _self_test() -> None:
    scoreboard = {
        "schema": "research.forward_market_scoreboard_r1",
        "generated_at": "2026-09-12T00:00:00+00:00",
        "lanes": [
            {
                "program_id": "P249_P266",
                "paper_action": {"SOXX": 0.2916666667, "XSD": 0.0833333333, "XBI": 0.125, "XPH": 0.0833333333,
                                 "AVDV": 0.125, "AVUV": 0.125, "DBC": 0.0625, "QQQ": 0.0625, "IGV": 0.0416666667},
            },
            {
                "program_id": "SEMICONDUCTOR_SHARED_RIDGE",
                "validation_grade": "PROSPECTIVE_SIGNAL_READY",
                "signal": {"positive_breadth": 12 / 13},
            },
            {
                "program_id": "HOMEBUILDERS",
                "signal": {"admitted_symbols": ["CCS", "MHO"], "duration_horizon_sessions_by_symbol": {"CCS": 5, "MHO": 60}},
            },
            {"program_id": "GENERALIZED_LARGECAP_RIDGE", "signal": {"positive_symbols": ["CAT"]}},
        ],
    }
    x = build(scoreboard)
    w = x["final_target_weights"]
    assert abs(sum(w.values()) - 1.0) < 1e-8
    assert abs(w["SOXX"] - 0.2333333334) < 1e-8
    assert x["sector_exposure"]["semiconductor"] <= SECTOR_CAP + EPS
    assert 0 < w.get("SMH", 0) <= NEW_COHORT_CAP
    assert abs(w["CCS"] - 0.025) < 1e-8 and abs(w["MHO"] - 0.025) < 1e-8
    assert x["tactical_used"] <= TACTICAL_BUDGET + EPS
    assert w["CASH"] >= CASH_FLOOR - EPS
    assert all(row["target_weight"] <= SINGLE_NAME_CAP + EPS for row in x["position_actions_vs_prior_allocator_target"] if row["symbol"] in {"CCS", "MHO"})

    missing_native = {
        "schema": scoreboard["schema"],
        "lanes": [scoreboard["lanes"][0]],
    }
    y = build(missing_native)
    assert abs(y["final_target_weights"]["CASH"] - 0.20) < 1e-8
    assert y["tactical_used"] == 0.0
    print("FORWARD_DETERMINISTIC_ALLOCATOR_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scoreboard")
    p.add_argument("--prior")
    p.add_argument("--output")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        _self_test()
        return
    if not args.scoreboard or not args.output:
        p.error("--scoreboard and --output are required unless --self-test is used")
    scoreboard = json.loads(Path(args.scoreboard).read_text(encoding="utf-8"))
    prior = None
    if args.prior and Path(args.prior).is_file():
        prior = json.loads(Path(args.prior).read_text(encoding="utf-8"))
    result = build(scoreboard, prior)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "policy_id": result["policy_id"],
        "tactical_used": result["tactical_used"],
        "cash_weight": result["cash_weight"],
        "targets": result["final_target_weights"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
