from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

P160_SCHEMA = "research.p160_forward_observer_r1"
CURRENCY_SCHEMA = "research.currency_hedge_mechanism_forward_r1"
CURRENCY_OVERLAY_SCHEMA = "research.currency_hedge_allocator_overlay_forward_r1"


def _guard_boundaries(name: str, x: dict[str, Any]) -> dict[str, Any]:
    b = x.get("boundaries") or {}
    if b.get("allocation_authority") is not False or b.get("promotion_authority") is not False:
        raise RuntimeError(f"{name} gained forbidden allocation/promotion authority")
    return b


def _strict_source_day(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _lane_p160(x: dict[str, Any]) -> dict[str, Any]:
    if x.get("schema") != P160_SCHEMA:
        raise RuntimeError("unexpected P160 observer schema")
    b = _guard_boundaries("P160 observer", x)
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
            "Observer eligibility is not earned forward credit; original issuer and funded NAV remain unadmitted. No allocator authority."
        ),
        "scientific_forward_credit": False,
        "observer_declared_prospective_eligibility": bool(x.get("scientific_forward_credit", False)),
        "forward_credit_stage": "SOURCE_ONLY_ORIGINAL_ISSUER_UNADMITTED",
        "validation_grade": x.get("state"),
        "scorecard": None,
        "decision_use": x.get("decision_use"),
        "benchmarks": x.get("benchmarks", {}),
        "boundaries": b,
    }


def _lane_currency(x: dict[str, Any]) -> dict[str, Any]:
    if x.get("schema") != CURRENCY_SCHEMA:
        raise RuntimeError("unexpected currency-hedge observer schema")
    b = _guard_boundaries("currency-hedge observer", x)
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
            "market_sessions_observed_including_entry": x.get("market_sessions_observed_including_entry", x.get("forward_sessions", 0)),
            "elapsed_close_to_close_sessions": x.get("elapsed_close_to_close_sessions", max(0, int(x.get("forward_sessions", 0) or 0) - 1)),
            "clock_semantics": "cross-program comparisons use elapsed_close_to_close_sessions; forward_sessions is retained as legacy inclusive-entry count",
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


def _lane_currency_overlay(x: dict[str, Any]) -> dict[str, Any]:
    if x.get("schema") != CURRENCY_OVERLAY_SCHEMA:
        raise RuntimeError("unexpected currency-hedge allocator-overlay schema")
    b = _guard_boundaries("currency-hedge allocator overlay", x)
    contract = x.get("contract") or {}
    if contract.get("funding_source") != "CASH_ONLY" or contract.get("leverage") is not False:
        raise RuntimeError("currency-hedge allocator overlay funding/leverage boundary changed")
    if b.get("allocator_mutation") is not False:
        raise RuntimeError("currency-hedge allocator overlay gained allocator mutation authority")
    requested = x.get("market_data_asof")
    latest = x.get("latest_common_market_date")
    common_precedes = bool(requested and latest and str(latest)[:10] < str(requested)[:10])
    return {
        "program_id": x["program_id"],
        "kind": "portfolio_level_currency_hedge_allocator_challenger",
        "signal_date": x.get("registered_at_date"),
        "signal": {
            "overlay_weight": contract.get("overlay_weight"),
            "funding_source": contract.get("funding_source"),
            "hedged_challenger": (x.get("positions") or {}).get("hedged_challenger", {}),
            "unhedged_matched_control": (x.get("positions") or {}).get("unhedged_matched_control", {}),
        },
        "timing": {
            "entry_date": x.get("entry_date"),
            "forward_sessions": x.get("forward_sessions", 0),
            "market_sessions_observed_including_entry": x.get("market_sessions_observed_including_entry", x.get("forward_sessions", 0)),
            "elapsed_close_to_close_sessions": x.get("elapsed_close_to_close_sessions", max(0, int(x.get("forward_sessions", 0) or 0) - 1)),
            "clock_semantics": "cross-program comparisons use elapsed_close_to_close_sessions; forward_sessions is retained as legacy inclusive-entry count",
            "entry_rule": contract.get("entry_rule"),
            "holding_rule": contract.get("holding_rule"),
            "requested_market_data_asof": requested,
            "latest_common_market_date": latest,
        },
        "source_health": {
            "requested_market_data_asof": requested,
            "latest_common_market_date": latest,
            "common_calendar_precedes_requested_asof": common_precedes,
            "interpretation": "Date discrepancy requires session/event review; it is not itself proof of absent data or losing alpha.",
        },
        "paper_action": {"status": "OBSERVE_ONLY", "portfolio_authority": False},
        "action_text": (
            "Test whether a 5% cash-funded HEFA/DBEF overlay improves the frozen allocator beyond both the unchanged "
            "allocator and an equal IEFA/EFA overlay. No leverage and no allocator mutation."
        ),
        "scientific_forward_credit": bool(x.get("scientific_forward_credit", False)),
        "validation_grade": x.get("state"),
        "scorecard": x.get("scorecard"),
        "decision_use": x.get("decision_use"),
        "benchmarks": {
            "incumbent": contract.get("incumbent"),
            "matched": contract.get("matched_control"),
            "opportunity": contract.get("opportunity_control"),
            "portfolio_roundtrip_cost_bps_if_flattened_now": (
                ((x.get("scorecard") or {}).get("cost_interpretation") or {}).get("portfolio_roundtrip_cost_bps_if_flattened_now")
            ),
        },
        "boundaries": b,
    }


def enrich(
    scoreboard: dict[str, Any],
    p160: dict[str, Any],
    currency: dict[str, Any],
    currency_overlay: dict[str, Any],
) -> dict[str, Any]:
    lanes = list(scoreboard.get("lanes") or [])
    additions = [_lane_p160(p160), _lane_currency(currency), _lane_currency_overlay(currency_overlay)]
    ids = {row["program_id"] for row in additions}
    lanes = [row for row in lanes if row.get("program_id") not in ids] + additions
    scoreboard["lanes"] = lanes
    freshness = scoreboard.setdefault("freshness", {})
    overlay_source_review = additions[-1]["source_health"]["common_calendar_precedes_requested_asof"]
    freshness["currency_overlay_common_calendar_precedes_requested_asof"] = overlay_source_review
    # An active currency mechanism can be one completed source session behind
    # the scoreboard even when both report the same market_data_asof label.
    # Preserve its frozen scorecard, but never present it as current without
    # the producer's own completed-session clock.
    currency_active = currency.get("state") == "PROSPECTIVE_OPEN"
    currency_requested = _strict_source_day(currency.get("market_data_asof"))
    currency_latest = _strict_source_day(currency.get("latest_common_market_date"))
    scoreboard_latest = _strict_source_day(freshness.get("common_market_data_asof"))
    currency_clock_missing = currency_active and (currency_requested is None or currency_latest is None)
    # The direct producer declares inclusive-entry and elapsed clocks separately.
    # Reject a missing, boolean, negative, or internally inconsistent active
    # source count; a same-day date label alone cannot repair it.
    counts = [currency.get(k) for k in (
        "forward_sessions", "market_sessions_observed_including_entry",
        "elapsed_close_to_close_sessions"
    )]
    currency_count_invalid = bool(currency_active and (
        any(type(v) is not int or v < 0 for v in counts) or
        (all(type(v) is int for v in counts) and
         (counts[0] != counts[1] or counts[2] != max(0, counts[0] - 1)))
    ))
    currency_own_lag = bool(currency_active and currency_latest and currency_requested
                            and currency_latest < currency_requested)
    currency_scoreboard_lag = bool(currency_active and currency_latest and scoreboard_latest
                                   and currency_latest < scoreboard_latest)
    currency_source_review = bool(currency_clock_missing or currency_count_invalid or currency_own_lag or currency_scoreboard_lag)
    currency_health = {
        "requested_market_data_asof": currency.get("market_data_asof"),
        "latest_common_market_date": currency.get("latest_common_market_date"),
        "scoreboard_common_market_data_asof": freshness.get("common_market_data_asof"),
        "missing_or_invalid_active_source_clock": bool(currency_clock_missing),
        "active_source_session_counts_inconsistent": currency_count_invalid,
        "producer_lags_own_requested_asof": currency_own_lag,
        "producer_lags_scoreboard_completed_asof": currency_scoreboard_lag,
        "source_review_required": currency_source_review,
        "interpretation": "Source-clock review only; not missing-bar proof, a strategy reversal, or alpha promotion.",
    }
    additions[1]["source_health"] = currency_health
    additions[1]["timing"]["latest_common_market_date"] = currency.get("latest_common_market_date")
    additions[1]["timing"]["market_data_asof"] = currency.get("market_data_asof")
    freshness["currency_mechanism_source_review_required"] = currency_source_review
    # Both observer source clocks must be considered before a green aggregate
    # freshness flag. A stale currency lane cannot inherit the global as-of.
    freshness["freshness_gap_visible"] = bool(
        freshness.get("freshness_gap_visible") or overlay_source_review or currency_source_review
    )

    coverage = scoreboard.setdefault("coverage", {})
    coverage["challenger_observers"] = {
        "P160_FIXED_P46_P47_COMBINATION": {
            "present": True,
            "state": p160.get("state"),
            "scientific_forward_credit": False,
            "observer_declared_prospective_eligibility": bool(p160.get("scientific_forward_credit", False)),
            "forward_credit_stage": "SOURCE_ONLY_ORIGINAL_ISSUER_UNADMITTED",
        },
        "DEVELOPED_EXUS_CURRENCY_HEDGE": {
            "present": True,
            "state": currency.get("state"),
            "scientific_forward_credit": bool(currency.get("scientific_forward_credit", False)),
            "source_review_required": currency_source_review,
        },
        "CURRENCY_HEDGE_ALLOCATOR_OVERLAY": {
            "present": True,
            "state": currency_overlay.get("state"),
            "scientific_forward_credit": bool(currency_overlay.get("scientific_forward_credit", False)),
        },
    }

    context = scoreboard.setdefault("actionable_context", [])
    context[:] = [row for row in context if row.get("source") not in ids]
    context.extend([
        {
            "source": "P160_FIXED_P46_P47_COMBINATION",
            "intel": "Frozen cross-asset + industry combination challenger",
            "state": (p160.get("paper_action") or {}).get("target_weights", {}),
            "authority": "prospective_eligibility_not_earned_credit" if p160.get("scientific_forward_credit") else "descriptive_prestart",
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
        {
            "source": "CURRENCY_HEDGE_ALLOCATOR_OVERLAY",
            "intel": "Cash-funded portfolio-level currency-hedge falsifier",
            "state": {
                "forward_state": currency_overlay.get("state"),
                "entry_date": currency_overlay.get("entry_date"),
                "requested_market_data_asof": currency_overlay.get("market_data_asof"),
                "latest_common_market_date": currency_overlay.get("latest_common_market_date"),
                "scorecard": currency_overlay.get("scorecard"),
            },
            "authority": "prospective_validation_only",
        },
    ])

    chain = scoreboard.setdefault("decision_chain", {})
    chain["construction_challengers"] = {
        "P160": {
            "state": p160.get("state"),
            "target_weights": (p160.get("paper_action") or {}).get("target_weights", {}),
            "scientific_forward_credit": False,
            "observer_declared_prospective_eligibility": bool(p160.get("scientific_forward_credit", False)),
            "forward_credit_stage": "SOURCE_ONLY_ORIGINAL_ISSUER_UNADMITTED",
            "role": "independent_validation_not_allocation",
        }
    }
    div = chain.setdefault("diversification", {})
    div["CURRENCY_HEDGE"] = {
        "state": currency.get("state"),
        "regime_context": currency.get("regime_context", {}),
        "scorecard": currency.get("scorecard"),
        "source_health": currency_health,
        "role": "matched-control_mechanism_challenger",
    }
    div["CURRENCY_HEDGE_ALLOCATOR_OVERLAY"] = {
        "state": currency_overlay.get("state"),
        "entry_date": currency_overlay.get("entry_date"),
        "forward_sessions": currency_overlay.get("forward_sessions", 0),
        "market_sessions_observed_including_entry": currency_overlay.get("market_sessions_observed_including_entry", currency_overlay.get("forward_sessions", 0)),
        "elapsed_close_to_close_sessions": currency_overlay.get("elapsed_close_to_close_sessions", max(0, int(currency_overlay.get("forward_sessions", 0) or 0) - 1)),
        "scorecard": currency_overlay.get("scorecard"),
        "funding_source": (currency_overlay.get("contract") or {}).get("funding_source"),
        "overlay_weight": (currency_overlay.get("contract") or {}).get("overlay_weight"),
        "requested_market_data_asof": currency_overlay.get("market_data_asof"),
        "latest_common_market_date": currency_overlay.get("latest_common_market_date"),
        "role": "portfolio_level_matched_control_challenger",
    }
    realized = chain.setdefault("realized_excess", {})
    mechanism = (currency.get("scorecard") or {}).get("mechanism") or {}
    realized["currency_hedge_mean_matched_excess_bps"] = mechanism.get("mean_matched_excess_if_flattened_now_bps")
    realized["currency_hedge_opportunity_excess_vs_spy_bps"] = mechanism.get("opportunity_excess_vs_SPY_bps")
    overlay_score = currency_overlay.get("scorecard") or {}
    overlay_hedged = overlay_score.get("hedged_challenger") or {}
    overlay_attr = overlay_score.get("mechanism_attribution") or {}
    realized["currency_overlay_excess_vs_incumbent_bps"] = overlay_hedged.get("excess_vs_incumbent_bps")
    realized["currency_overlay_hedged_minus_unhedged_bps"] = overlay_attr.get("hedged_minus_unhedged_bps")
    realized["currency_overlay_hedged_minus_spy_bps"] = overlay_attr.get("hedged_minus_spy_overlay_bps")

    interpretation = scoreboard.setdefault("interpretation", {})
    interpretation["challenger_observers_do_not_grant_allocator_authority"] = True
    interpretation["p160_prestart_shadow_is_not_forward_credit"] = True
    interpretation["p160_observer_eligibility_is_not_earned_forward_credit"] = True
    interpretation["currency_regime_context_is_not_timing_authority"] = True
    interpretation["currency_overlay_is_observation_not_allocator_mutation"] = True
    interpretation["currency_overlay_is_cash_funded_without_leverage"] = True
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
    overlay = {
        "schema": CURRENCY_OVERLAY_SCHEMA,
        "program_id": "CURRENCY_HEDGE_ALLOCATOR_OVERLAY",
        "registered_at_date": "2026-09-13",
        "state": "AWAITING_ENTRY_SESSION",
        "scientific_forward_credit": True,
        "entry_date": None,
        "forward_sessions": 0,
        "contract": {
            "funding_source": "CASH_ONLY",
            "leverage": False,
            "overlay_weight": .05,
            "incumbent": "frozen allocator",
            "matched_control": "unhedged overlay",
            "opportunity_control": "SPY overlay",
            "entry_rule": "first common session after registration",
            "holding_rule": "hold frozen weights",
        },
        "positions": {
            "hedged_challenger": {"CASH": .05, "HEFA": .025, "DBEF": .025},
            "unhedged_matched_control": {"CASH": .05, "IEFA": .025, "EFA": .025},
        },
        "scorecard": None,
        "decision_use": "test",
        "boundaries": {
            "allocation_authority": False,
            "promotion_authority": False,
            "allocator_mutation": False,
        },
    }
    out = enrich(scoreboard, p160, currency, overlay)
    by_id = {x["program_id"]: x for x in out["lanes"]}
    assert by_id["P160_FIXED_P46_P47_COMBINATION"]["validation_grade"] == "PRESTART_DESCRIPTIVE_SHADOW"
    assert by_id["DEVELOPED_EXUS_CURRENCY_HEDGE"]["validation_grade"] == "AWAITING_ENTRY_SESSION"
    assert by_id["CURRENCY_HEDGE_ALLOCATOR_OVERLAY"]["validation_grade"] == "AWAITING_ENTRY_SESSION"
    assert out["decision_chain"]["diversification"]["CURRENCY_HEDGE"]["regime_context"]["timing_authority"] is False
    assert out["decision_chain"]["diversification"]["CURRENCY_HEDGE_ALLOCATOR_OVERLAY"]["funding_source"] == "CASH_ONLY"
    assert out["interpretation"]["challenger_observers_do_not_grant_allocator_authority"] is True
    assert out["interpretation"]["currency_overlay_is_observation_not_allocator_mutation"] is True
    assert by_id["DEVELOPED_EXUS_CURRENCY_HEDGE"]["timing"]["elapsed_close_to_close_sessions"] == 0
    assert by_id["CURRENCY_HEDGE_ALLOCATOR_OVERLAY"]["timing"]["elapsed_close_to_close_sessions"] == 0
    lagged = dict(overlay, market_data_asof="2026-10-21", latest_common_market_date="2026-10-19")
    lane = _lane_currency_overlay(lagged)
    assert lane["source_health"]["common_calendar_precedes_requested_asof"] is True
    assert lane["timing"]["latest_common_market_date"] == "2026-10-19"
    assert lane["scorecard"] is None and lane["boundaries"]["allocator_mutation"] is False
    lagged_scoreboard = enrich({"lanes": [], "coverage": {}, "actionable_context": [], "decision_chain": {}, "interpretation": {}, "freshness": {"freshness_gap_visible": False}}, p160, currency, lagged)
    assert lagged_scoreboard["freshness"]["currency_overlay_common_calendar_precedes_requested_asof"] is True
    assert lagged_scoreboard["freshness"]["freshness_gap_visible"] is True
    assert "not itself proof of absent data or losing alpha" in lagged_scoreboard["lanes"][-1]["source_health"]["interpretation"]
    assert out["freshness"]["freshness_gap_visible"] is False
    # Exact current-source defect: an active mechanism's 33/32 source clock
    # must not inherit a 34/33 completed scoreboard clock or same-day label.
    stale_currency = dict(currency, state="PROSPECTIVE_OPEN",
                          market_data_asof="2026-10-29",
                          latest_common_market_date="2026-10-28",
                          forward_sessions=33, market_sessions_observed_including_entry=33,
                          elapsed_close_to_close_sessions=32)
    currency_board = {"lanes": [], "coverage": {}, "actionable_context": [],
                      "decision_chain": {}, "interpretation": {},
                      "freshness": {"common_market_data_asof": "2026-10-29",
                                    "freshness_gap_visible": False}}
    stale_currency_out = enrich(currency_board, p160, stale_currency, overlay)
    assert stale_currency_out["freshness"]["currency_mechanism_source_review_required"] is True
    assert stale_currency_out["freshness"]["freshness_gap_visible"] is True
    assert stale_currency_out["coverage"]["challenger_observers"]["DEVELOPED_EXUS_CURRENCY_HEDGE"]["source_review_required"] is True
    fresh_currency = dict(stale_currency, latest_common_market_date="2026-10-29",
                          forward_sessions=34, market_sessions_observed_including_entry=34,
                          elapsed_close_to_close_sessions=33)
    fresh_currency_out = enrich({"lanes": [], "coverage": {}, "actionable_context": [],
                                 "decision_chain": {}, "interpretation": {},
                                 "freshness": {"common_market_data_asof": "2026-10-29",
                                               "freshness_gap_visible": False}},
                                p160, fresh_currency, overlay)
    assert fresh_currency_out["freshness"]["currency_mechanism_source_review_required"] is False
    assert fresh_currency_out["freshness"]["freshness_gap_visible"] is False
    inconsistent_currency = dict(fresh_currency, elapsed_close_to_close_sessions=32)
    inconsistent_out = enrich({"lanes": [], "coverage": {}, "actionable_context": [],
                               "decision_chain": {}, "interpretation": {},
                               "freshness": {"common_market_data_asof": "2026-10-29",
                                             "freshness_gap_visible": False}},
                              p160, inconsistent_currency, overlay)
    assert inconsistent_out["freshness"]["currency_mechanism_source_review_required"] is True
    assert inconsistent_out["lanes"][-2]["source_health"]["active_source_session_counts_inconsistent"] is True
    # An observer may be prospectively eligible without an independently
    # authenticated original adjusted-source/calendar issuer or funded NAV.
    p160_eligible = dict(p160, state="PROSPECTIVE_ELIGIBLE", scientific_forward_credit=True)
    eligible_out = enrich(out, p160_eligible, currency, overlay)
    p160_lane = next(row for row in eligible_out["lanes"] if row["program_id"] == p160_eligible["program_id"])
    assert p160_lane["validation_grade"] == "PROSPECTIVE_ELIGIBLE"
    assert p160_lane["observer_declared_prospective_eligibility"] is True
    assert p160_lane["scientific_forward_credit"] is False
    assert p160_lane["scorecard"] is None
    assert p160_lane["forward_credit_stage"] == "SOURCE_ONLY_ORIGINAL_ISSUER_UNADMITTED"
    assert eligible_out["coverage"]["challenger_observers"][p160_eligible["program_id"]]["scientific_forward_credit"] is False
    assert eligible_out["decision_chain"]["construction_challengers"]["P160"]["scientific_forward_credit"] is False
    assert eligible_out["interpretation"]["p160_observer_eligibility_is_not_earned_forward_credit"] is True
    print("FORWARD_CHALLENGER_SCOREBOARD_ENRICHMENT_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scoreboard")
    p.add_argument("--p160")
    p.add_argument("--currency")
    p.add_argument("--currency-overlay")
    p.add_argument("--output")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if not all((args.scoreboard, args.p160, args.currency, args.currency_overlay, args.output)):
        p.error("scoreboard, p160, currency, currency-overlay and output are required")
    scoreboard = json.loads(Path(args.scoreboard).read_text())
    p160 = json.loads(Path(args.p160).read_text())
    currency_raw = Path(args.currency).read_bytes()
    currency = json.loads(currency_raw)
    currency_overlay = json.loads(Path(args.currency_overlay).read_text())
    out = enrich(scoreboard, p160, currency, currency_overlay)
    # Bind the actual producer bytes, not just a global market-data-asof label.
    # This lets private owning consumers detect same-day producer revisions too.
    out.setdefault("input_lineage", {})["currency_mechanism_source"] = {
        "sha256": hashlib.sha256(currency_raw).hexdigest(),
        "market_data_asof": currency.get("market_data_asof"),
        "latest_common_market_date": currency.get("latest_common_market_date"),
        "forward_sessions": currency.get("forward_sessions"),
        "market_sessions_observed_including_entry": currency.get("market_sessions_observed_including_entry"),
        "elapsed_close_to_close_sessions": currency.get("elapsed_close_to_close_sessions"),
        "source_identity_only_not_issuer_or_rights_admission": True,
    }
    Path(args.output).write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({
        "challenger_observers": out["coverage"]["challenger_observers"],
        "allocator_authority": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
