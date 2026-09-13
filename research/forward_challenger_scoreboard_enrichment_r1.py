from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

P160_SCHEMA = "research.p160_forward_observer_r1"
CURRENCY_SCHEMA = "research.currency_hedge_mechanism_forward_r1"


def _lane_p160(x: dict[str, Any]) -> dict[str, Any]:
    if x.get("schema") != P160_SCHEMA:
        raise RuntimeError("unexpected P160 observer schema")
    b = x.get("boundaries") or {}
    if b.get("allocation_authority") is not False or b.get("promotion_authority") is not False:
        raise RuntimeError("P160 observer gained forbidden authority")
    return {
        "program_id": x["program_id"],
        "kind": "fixed_cross_asset_industry_combination_challenger",
        "signal_date": x.get("signal_month_end"),
        "signal": {
            "p46_cross_asset_top2": (x.get("signal") or {}).get("p46_cross_asset_top2", []),
            "p47_industry_top3": (x.get("signal") or {}).get("p47_industry_top3", []),
        },
        "timing": x.get("timing", {}),
        "paper_action": x.get("paper_action", {}),
        "action_text": (
            f"Shadow frozen P160 only: {(x.get('paper_action') or {}).get('target_weights', {})}. "
            "No scientific credit before the declared boundary and no allocator authority."
        ),
        "scientific_forward_credit": bool(x.get("scientific_forward_credit", False)),
        "validation_grade": x.get("state"),
        "scorecard": None,
        "decision_use": x.get("decision_use"),
        "benchmarks": x.get("benchmarks", {}),
        "boundaries": b,
    }


def _lane_currency(x: dict[str, Any]) -> dict[str, Any]:
    if x.get("schema") != CURRENCY_SCHEMA:
        raise RuntimeError("unexpected currency-hedge observer schema")
    b = x.get("boundaries") or {}
    if b.get("allocation_authority") is not False or b.get("promotion_authority") is not False:
        raise RuntimeError("currency-hedge observer gained forbidden authority")
    return {
        "program_id": x["program_id"],
        "kind": "developed_exus_currency_hedge_mechanism_challenger",
        "signal_date": x.get("registered_at_date"),
        "signal": {
            "implementations": (x.get("contract") or {}).get("implementations", {}),
            "regime_context": x.get("regime_context", {}),
        },
        "timing": {
            "entry": x.get("entry", {}),
            "forward_sessions": x.get("forward_sessions", 0),
            "regime_is_not_timing_gate": (x.get("contract") or {}).get("regime_is_not_timing_gate"),
        },
        "paper_action": {"status": "OBSERVE_ONLY", "portfolio_authority": False},
        "action_text": (
            "Track HEFA vs IEFA and DBEF vs EFA prospectively; SPY is opportunity cost only. "
            "Lagged UUP regime is explanatory context, not a trade gate."
        ),
        "scientific_forward_credit": bool(x.get("scientific_forward_credit", False)),
        "validation_grade": x.get("state"),
        "scorecard": x.get("scorecard"),
        "decision_use": x.get("decision_use"),
        "benchmarks": {
            "matched": {"HEFA": "IEFA", "DBEF": "EFA"},
            "opportunity": "SPY",
            "cost_bps_each_endpoint": (x.get("contract") or {}).get("cost_bps_each_endpoint"),
        },
        "boundaries": b,
    }


def enrich(scoreboard: dict[str, Any], p160: dict[str, Any], currency: dict[str, Any]) -> dict[str, Any]:
    lanes = list(scoreboard.get("lanes") or [])
    additions = [_lane_p160(p160), _lane_currency(currency)]
    ids = {row["program_id"] for row in additions}
    lanes = [row for row in lanes if row.get("program_id") not in ids] + additions
    scoreboard["lanes"] = lanes

    coverage = scoreboard.setdefault("coverage", {})
    coverage["challenger_observers"] = {
        "P160_FIXED_P46_P47_COMBINATION": {
            "present": True,
            "state": p160.get("state"),
            "scientific_forward_credit": bool(p160.get("scientific_forward_credit", False)),
        },
        "DEVELOPED_EXUS_CURRENCY_HEDGE": {
            "present": True,
            "state": currency.get("state"),
            "scientific_forward_credit": bool(currency.get("scientific_forward_credit", False)),
        },
    }

    context = scoreboard.setdefault("actionable_context", [])
    context[:] = [row for row in context if row.get("source") not in ids]
    context.extend([
        {
            "source": "P160_FIXED_P46_P47_COMBINATION",
            "intel": "Frozen cross-asset + industry combination challenger",
            "state": (p160.get("paper_action") or {}).get("target_weights", {}),
            "authority": "descriptive_prestart" if not p160.get("scientific_forward_credit") else "prospective_validation_only",
        },
        {
            "source": "DEVELOPED_EXUS_CURRENCY_HEDGE",
            "intel": "Replicated currency-hedge mechanism challenger",
            "state": {
                "forward_state": currency.get("state"),
                "regime_context": currency.get("regime_context", {}),
            },
            "authority": "prospective_validation_only",
        },
    ])

    chain = scoreboard.setdefault("decision_chain", {})
    chain["construction_challengers"] = {
        "P160": {
            "state": p160.get("state"),
            "target_weights": (p160.get("paper_action") or {}).get("target_weights", {}),
            "scientific_forward_credit": bool(p160.get("scientific_forward_credit", False)),
            "role": "independent_validation_not_allocation",
        }
    }
    div = chain.setdefault("diversification", {})
    div["CURRENCY_HEDGE"] = {
        "state": currency.get("state"),
        "regime_context": currency.get("regime_context", {}),
        "scorecard": currency.get("scorecard"),
        "role": "matched-control_mechanism_challenger",
    }
    realized = chain.setdefault("realized_excess", {})
    mechanism = (currency.get("scorecard") or {}).get("mechanism") or {}
    realized["currency_hedge_mean_matched_excess_bps"] = mechanism.get("mean_matched_excess_if_flattened_now_bps")
    realized["currency_hedge_opportunity_excess_vs_spy_bps"] = mechanism.get("opportunity_excess_vs_SPY_bps")

    interpretation = scoreboard.setdefault("interpretation", {})
    interpretation["challenger_observers_do_not_grant_allocator_authority"] = True
    interpretation["p160_prestart_shadow_is_not_forward_credit"] = True
    interpretation["currency_regime_context_is_not_timing_authority"] = True
    return scoreboard


def self_test() -> None:
    scoreboard = {
        "lanes": [{"program_id": "P249_P266"}],
        "coverage": {},
        "actionable_context": [],
        "decision_chain": {"diversification": {}, "realized_excess": {}},
        "interpretation": {},
    }
    p160 = {
        "schema": P160_SCHEMA,
        "program_id": "P160_FIXED_P46_P47_COMBINATION",
        "signal_month_end": "2026-08-31",
        "state": "PRESTART_DESCRIPTIVE_SHADOW",
        "scientific_forward_credit": False,
        "signal": {"p46_cross_asset_top2": ["DBC", "QQQ"], "p47_industry_top3": ["IWM", "XBI", "IGV"]},
        "paper_action": {"target_weights": {"DBC": .25, "QQQ": .25, "IWM": 1/6, "XBI": 1/6, "IGV": 1/6}, "portfolio_authority": False},
        "timing": {},
        "benchmarks": {},
        "decision_use": "test",
        "boundaries": {"allocation_authority": False, "promotion_authority": False},
    }
    currency = {
        "schema": CURRENCY_SCHEMA,
        "program_id": "DEVELOPED_EXUS_CURRENCY_HEDGE",
        "registered_at_date": "2026-09-13",
        "state": "AWAITING_ENTRY_SESSION",
        "scientific_forward_credit": True,
        "contract": {"implementations": {"HEFA": {"matched_control": "IEFA"}, "DBEF": {"matched_control": "EFA"}}, "regime_is_not_timing_gate": True, "cost_bps_each_endpoint": 25},
        "regime_context": {"state": "strong_dollar", "timing_authority": False},
        "entry": {"date": None},
        "scorecard": None,
        "decision_use": "test",
        "boundaries": {"allocation_authority": False, "promotion_authority": False},
    }
    out = enrich(scoreboard, p160, currency)
    by_id = {x["program_id"]: x for x in out["lanes"]}
    assert by_id["P160_FIXED_P46_P47_COMBINATION"]["validation_grade"] == "PRESTART_DESCRIPTIVE_SHADOW"
    assert by_id["DEVELOPED_EXUS_CURRENCY_HEDGE"]["validation_grade"] == "AWAITING_ENTRY_SESSION"
    assert out["decision_chain"]["diversification"]["CURRENCY_HEDGE"]["regime_context"]["timing_authority"] is False
    assert out["interpretation"]["challenger_observers_do_not_grant_allocator_authority"] is True
    print("FORWARD_CHALLENGER_SCOREBOARD_ENRICHMENT_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scoreboard")
    p.add_argument("--p160")
    p.add_argument("--currency")
    p.add_argument("--output")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if not all((args.scoreboard, args.p160, args.currency, args.output)):
        p.error("scoreboard, p160, currency and output are required")
    scoreboard = json.loads(Path(args.scoreboard).read_text())
    p160 = json.loads(Path(args.p160).read_text())
    currency = json.loads(Path(args.currency).read_text())
    out = enrich(scoreboard, p160, currency)
    Path(args.output).write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({
        "challenger_observers": out["coverage"]["challenger_observers"],
        "allocator_authority": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
