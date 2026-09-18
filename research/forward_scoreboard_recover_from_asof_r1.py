from __future__ import annotations

"""Compose a recovered historical forward scoreboard from canonical helpers.

The structural shell must come from a real bracketing historical scoreboard.
Only lanes backed by exact as-of durable evidence are replaced. The result is
explicitly marked as a historical reconstruction and never grants allocation,
promotion, broker, runtime, or live-trading authority.
"""

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from forward_challenger_scoreboard_enrichment_r1 import enrich
from forward_market_scoreboard_r1 import (
    ADAPTER_SCHEMA,
    EXPECTED_PRIVATE_ADAPTERS,
    _challenger,
    _decision_chain,
    _native_lane,
    _p249,
    _prospective_state,
)
from forward_scoreboard_lineage_r1 import annotate_scoreboard

SCOREBOARD_SCHEMA = "research.forward_market_scoreboard_r1"


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    return json.loads(raw), raw


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _adapters(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in root.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != ADAPTER_SCHEMA:
            continue
        pid = str(payload.get("program_id") or "")
        if pid in EXPECTED_PRIVATE_ADAPTERS:
            out[pid] = payload
    missing = sorted(set(EXPECTED_PRIVATE_ADAPTERS) - set(out))
    if missing:
        raise RuntimeError(f"missing native adapters: {missing}")
    return out


def _replace_lanes(
    scoreboard: dict[str, Any],
    p249: dict[str, Any],
    p558: dict[str, Any],
    clo: dict[str, Any],
    adapters: dict[str, dict[str, Any]],
    ledger: dict[str, Any],
) -> None:
    replacements: dict[str, dict[str, Any]] = {
        "P249_P266": _p249(p249),
        "P558": _challenger(p558, "P558", "KMLM"),
        "SENIOR_CLO": _challenger(clo, "SENIOR_CLO", "JAAA"),
    }
    for program in EXPECTED_PRIVATE_ADAPTERS:
        replacements[program] = _native_lane(
            adapters[program],
            _prospective_state(ledger, program),
        )

    existing = list(scoreboard.get("lanes") or [])
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lane in existing:
        pid = str(lane.get("program_id") or "")
        if pid in replacements:
            output.append(replacements[pid])
            seen.add(pid)
        else:
            output.append(lane)
    for pid, lane in replacements.items():
        if pid not in seen:
            output.append(lane)
    scoreboard["lanes"] = output


def recover(
    base_scoreboard: dict[str, Any],
    p249: dict[str, Any],
    p558: dict[str, Any],
    clo: dict[str, Any],
    adapters: dict[str, dict[str, Any]],
    ledger: dict[str, Any],
    ledger_raw: bytes,
    p160: dict[str, Any],
    currency: dict[str, Any],
    currency_overlay: dict[str, Any],
    session_date: str,
    recovered_at: str,
    base_ref: str | None,
) -> dict[str, Any]:
    if base_scoreboard.get("schema") != SCOREBOARD_SCHEMA:
        raise RuntimeError(f"unexpected base scoreboard schema {base_scoreboard.get('schema')}")

    score = copy.deepcopy(base_scoreboard)
    _replace_lanes(score, p249, p558, clo, adapters, ledger)
    score["decision_chain"] = _decision_chain(list(score.get("lanes") or []))
    score = enrich(score, p160, currency, currency_overlay)
    score = annotate_scoreboard(score, ledger, ledger_raw)

    # No large-cap prospective observer existed on the recovered date. The
    # adapter signal remains visible, while the lane stays context-only.
    largecap = next(
        (x for x in score.get("lanes", []) if x.get("program_id") == "GENERALIZED_LARGECAP_RIDGE"),
        None,
    )
    if largecap is not None:
        largecap.pop("forward_observation", None)
        largecap.pop("forward_scorecard", None)
        largecap.pop("formal_resolved_scorecard", None)
        largecap["observation_status"] = "CONTEXT_ONLY"
        largecap["evidence_grade"] = "NO_REGISTERED_PROSPECTIVE_COHORT"

    score["generated_at"] = recovered_at
    score["historical_recovery"] = {
        "session_date": session_date,
        "recovered_at": recovered_at,
        "kind": "RECONSTRUCTED_FROM_DURABLE_TAPES_AND_FROZEN_CONTRACTS",
        "original_scoreboard_published": False,
        "base_scoreboard_ref": base_ref,
        "allocation_authority": False,
        "promotion_authority": False,
        "broker_action": False,
        "live_trading_change": False,
        "notes": [
            "P249/P266, KMLM and JAAA were truncated from durable dated native observations.",
            "Homebuilders and Semiconductor were regenerated through the canonical prospective ledger at the requested as-of date.",
            "Currency mechanism and portfolio overlay were regenerated through their canonical as-of observers.",
            "P46/P160 and other structural fields were inherited from the real bracketing historical scoreboard.",
            "Generalized Large-Cap retains its historical corroboration-only state; no retroactive prospective observer credit is created.",
        ],
    }
    score.setdefault("coverage", {})["historical_recovery"] = {
        "session_date": session_date,
        "complete_model_lane_count": len(score.get("lanes") or []),
        "reporting_only": True,
    }
    score.setdefault("interpretation", {})[
        "historical_recovery_is_not_original_publication_or_forward_credit"
    ] = True
    return score


def self_test() -> None:
    base = {
        "schema": SCOREBOARD_SCHEMA,
        "generated_at": "2026-09-14T00:00:00+00:00",
        "lanes": [
            {"program_id": "P46", "boundaries": {}},
            {"program_id": "P249_P266"},
            {"program_id": "P558"},
            {"program_id": "SENIOR_CLO"},
            {"program_id": "SEMICONDUCTOR_SHARED_RIDGE"},
            {"program_id": "HOMEBUILDERS"},
            {"program_id": "GENERALIZED_LARGECAP_RIDGE"},
        ],
        "coverage": {},
        "decision_chain": {},
        "actionable_context": [],
        "interpretation": {},
    }
    p249 = {
        "forward": {
            "observations": [{"satellite_increment_net": 0.01}],
            "p249_core_net": {"days": 1, "cumulative_return": 0.01, "annualized_vol": None},
            "p249_plus_p266_net": {"days": 1, "cumulative_return": 0.02, "annualized_vol": None},
            "satellite_increment_cumulative": 0.01,
        },
        "current_state": {"p249_core": {}, "p266": {}, "p249_plus_p266": {}},
        "boundaries": {},
    }
    challenger = {
        "forward": {
            "challenger_if_flattened_now": {"days": 1, "cumulative_return": 0.0, "max_drawdown": 0.0, "annualized_vol": None},
            "challenger_minus_incumbent_cumulative": 0.0,
            "challenger_minus_matched_cumulative": 0.0,
            "challenger_observations": [{"net_return": 0.0, "core_return": 0.0}],
            "matched_control_observations": [{"net_return": 0.0, "core_return": 0.0}],
        },
        "current_positions": {"challenger": {}},
        "contract": {"fixed_weight": 0.5},
        "boundaries": {},
    }
    adapters = {}
    for pid in EXPECTED_PRIVATE_ADAPTERS:
        adapters[pid] = {
            "schema": ADAPTER_SCHEMA,
            "program_id": pid,
            "signal_date": "2026-09-11",
            "signal": {},
            "timing": {},
            "paper_action": {"status": "NONE"},
            "validation": {},
            "boundaries": {
                "broker_action": False,
                "live_trading_change": False,
                "runtime_mutation": False,
                "promotion_authority": False,
                "allocation_authority": False,
            },
        }
    ledger = {
        "schema": "research.forward_prospective_cohort_ledger_r1",
        "generated_at": "2026-09-15T00:00:00+00:00",
        "market_data_asof": "2026-09-15",
        "cohorts": [],
        "summary": {},
    }
    p160 = {
        "schema": "research.p160_forward_observer_r1",
        "program_id": "P160_FIXED_P46_P47_COMBINATION",
        "signal_month_end": "2026-08-31",
        "state": "PRESTART_DESCRIPTIVE_SHADOW",
        "scientific_forward_credit": False,
        "paper_action": {"target_weights": {}},
        "signal": {},
        "timing": {},
        "boundaries": {
            "allocation_authority": False,
            "broker_action": False,
            "live_trading_change": False,
            "runtime_mutation": False,
            "promotion_authority": False,
        },
    }
    currency = {
        "schema": "research.currency_hedge_mechanism_forward_r1",
        "program_id": "DEVELOPED_EXUS_CURRENCY_HEDGE",
        "registered_at_date": "2026-09-13",
        "contract": {"implementations": {}, "regime_is_not_timing_gate": True},
        "state": "PROSPECTIVE_OPEN",
        "scientific_forward_credit": True,
        "scorecard": {},
        "regime_context": {},
        "entry": {"date": "2026-09-14"},
        "forward_sessions": 2,
        "boundaries": {
            "allocation_authority": False,
            "broker_action": False,
            "live_trading_change": False,
            "runtime_mutation": False,
            "promotion_authority": False,
        },
    }
    overlay = {
        "schema": "research.currency_hedge_allocator_overlay_forward_r1",
        "program_id": "CURRENCY_HEDGE_ALLOCATOR_OVERLAY",
        "registered_at_date": "2026-09-13",
        "state": "PROSPECTIVE_OPEN",
        "scientific_forward_credit": True,
        "scorecard": {},
        "entry_date": "2026-09-14",
        "forward_sessions": 2,
        "contract": {
            "funding_source": "CASH_ONLY",
            "overlay_weight": 0.05,
            "leverage": False,
            "entry_rule": "test",
            "holding_rule": "test",
        },
        "positions": {},
        "boundaries": {
            "allocation_authority": False,
            "allocator_mutation": False,
            "broker_action": False,
            "live_trading_change": False,
            "runtime_mutation": False,
            "promotion_authority": False,
        },
    }
    raw = (json.dumps(ledger, sort_keys=True) + "\n").encode()
    out = recover(
        base, p249, challenger, challenger, adapters, ledger, raw,
        p160, currency, overlay,
        "2026-09-15", "2026-09-18T00:00:00+00:00", "test-ref",
    )
    assert out["historical_recovery"]["original_scoreboard_published"] is False
    assert len(out["lanes"]) == 10
    by_id = {x["program_id"]: x for x in out["lanes"]}
    assert by_id["GENERALIZED_LARGECAP_RIDGE"]["observation_status"] == "CONTEXT_ONLY"
    print("FORWARD_SCOREBOARD_RECOVER_FROM_ASOF_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-scoreboard")
    p.add_argument("--base-ref")
    p.add_argument("--p249")
    p.add_argument("--p558")
    p.add_argument("--clo")
    p.add_argument("--native-adapter-dir")
    p.add_argument("--ledger")
    p.add_argument("--p160")
    p.add_argument("--currency")
    p.add_argument("--currency-overlay")
    p.add_argument("--session-date")
    p.add_argument("--output")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        self_test()
        return

    required = [
        args.base_scoreboard, args.p249, args.p558, args.clo,
        args.native_adapter_dir, args.ledger, args.p160,
        args.currency, args.currency_overlay, args.session_date, args.output,
    ]
    if any(x is None for x in required):
        p.error("all recovery inputs are required unless --self-test")

    base, _ = _read(Path(args.base_scoreboard))
    p249, _ = _read(Path(args.p249))
    p558, _ = _read(Path(args.p558))
    clo, _ = _read(Path(args.clo))
    ledger, ledger_raw = _read(Path(args.ledger))
    p160, _ = _read(Path(args.p160))
    currency, _ = _read(Path(args.currency))
    overlay, _ = _read(Path(args.currency_overlay))

    result = recover(
        base,
        p249,
        p558,
        clo,
        _adapters(Path(args.native_adapter_dir)),
        ledger,
        ledger_raw,
        p160,
        currency,
        overlay,
        args.session_date,
        datetime.now(timezone.utc).isoformat(),
        args.base_ref,
    )
    _write(Path(args.output), result)
    print(json.dumps({
        "session_date": args.session_date,
        "lane_count": len(result.get("lanes") or []),
        "recovery_kind": result["historical_recovery"]["kind"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
