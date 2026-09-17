from __future__ import annotations

"""Attach prospective-input lineage and observation-state visibility.

This module is deliberately observation/reporting only. It does not change model
signals, admission rules, horizons, portfolio weights, allocator authority, broker
actions, or promotion authority.
"""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCOREBOARD_SCHEMA = "research.forward_market_scoreboard_r1"
LEDGER_SCHEMA = "research.forward_prospective_cohort_ledger_r1"
ALLOCATOR_SCHEMA = "research.forward_deterministic_allocator_r1"

ACTIVE = "ACTIVE"
CONTEXT_ONLY = "CONTEXT_ONLY"
BLOCKED_NO_FROZEN_OBSERVATION_CONTRACT = "BLOCKED_NO_FROZEN_OBSERVATION_CONTRACT"

_CONTEXT_ONLY_PROGRAMS = {
    "P46",
    "GENERALIZED_LARGECAP_RIDGE",
    "P160_FIXED_P46_P47_COMBINATION",
}
_PROSPECTIVE_LEDGER_PROGRAMS = {
    "SEMICONDUCTOR_SHARED_RIDGE",
    "HOMEBUILDERS",
}
_ACTIVE_OBSERVERS = {
    "P249_P266",
    "P558",
    "SENIOR_CLO",
    "DEVELOPED_EXUS_CURRENCY_HEDGE",
    "CURRENCY_HEDGE_ALLOCATOR_OVERLAY",
}
_SLEEVE_TO_PROGRAM = {
    "P249_P266_CORE": "P249_P266",
    "SEMICONDUCTOR_SHARED_RIDGE_INDUSTRY_BOOK": "SEMICONDUCTOR_SHARED_RIDGE",
    "HOMEBUILDERS": "HOMEBUILDERS",
    "GENERALIZED_LARGECAP_RIDGE": "GENERALIZED_LARGECAP_RIDGE",
    "P46": "P46",
    "P558_KMLM_SUBSTITUTION": "P558",
    "SENIOR_CLO_JAAA_SUBSTITUTION": "SENIOR_CLO",
}


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    return json.loads(raw), raw


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _ledger_lineage(ledger: dict[str, Any], raw: bytes) -> dict[str, Any]:
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise RuntimeError(f"unexpected ledger schema {ledger.get('schema')}")
    return {
        "schema": LEDGER_SCHEMA,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "generated_at": ledger.get("generated_at"),
        "market_data_asof": ledger.get("market_data_asof"),
        "cohort_count": len(ledger.get("cohorts") or []),
    }


def _observation_status(lane: dict[str, Any]) -> str:
    program = str(lane.get("program_id") or "")
    if program in _CONTEXT_ONLY_PROGRAMS:
        return CONTEXT_ONLY
    if program in _PROSPECTIVE_LEDGER_PROGRAMS:
        prospective = lane.get("prospective_evidence") or {}
        if prospective.get("ledger_status") == "PRESENT":
            return ACTIVE
        return BLOCKED_NO_FROZEN_OBSERVATION_CONTRACT
    if program in _ACTIVE_OBSERVERS:
        return ACTIVE
    return CONTEXT_ONLY


def annotate_scoreboard(scoreboard: dict[str, Any], ledger: dict[str, Any], ledger_raw: bytes) -> dict[str, Any]:
    if scoreboard.get("schema") != SCOREBOARD_SCHEMA:
        raise RuntimeError(f"unexpected scoreboard schema {scoreboard.get('schema')}")
    lineage = _ledger_lineage(ledger, ledger_raw)
    scoreboard.setdefault("input_lineage", {})["prospective_ledger"] = lineage

    by_program = {str(c.get("program_id")): c for c in (ledger.get("cohorts") or [])}
    for lane in scoreboard.get("lanes") or []:
        program = str(lane.get("program_id") or "")
        status = _observation_status(lane)
        lane["observation_status"] = status
        lane_lineage: dict[str, Any] = {
            "prospective_ledger_sha256": lineage["sha256"],
            "prospective_ledger_generated_at": lineage.get("generated_at"),
            "market_data_asof": lineage.get("market_data_asof"),
        }
        cohort = by_program.get(program)
        if cohort:
            lane_lineage.update({
                "cohort_id": cohort.get("cohort_id"),
                "cohort_status": cohort.get("status"),
                "signal_date": cohort.get("signal_date"),
                "source_adapter_sha256": cohort.get("source_adapter_sha256"),
                "source_ref": cohort.get("source_ref"),
            })
        lane["observation_lineage"] = lane_lineage

    coverage = scoreboard.setdefault("coverage", {}).setdefault("prospective_ledger", {})
    coverage.update({
        "present": True,
        "generated_at": lineage.get("generated_at"),
        "market_data_asof": lineage.get("market_data_asof"),
        "sha256": lineage["sha256"],
    })
    scoreboard.setdefault("interpretation", {})["zero_weight_does_not_mean_inactive_observer"] = True
    return scoreboard


def _is_zero_weight_action(row: dict[str, Any]) -> bool:
    for key in ("target_weight", "family_weight"):
        if key in row and float(row.get(key) or 0.0) == 0.0:
            return True
    return False


def annotate_allocator(scoreboard: dict[str, Any], allocator: dict[str, Any]) -> dict[str, Any]:
    if scoreboard.get("schema") != SCOREBOARD_SCHEMA:
        raise RuntimeError(f"unexpected scoreboard schema {scoreboard.get('schema')}")
    if allocator.get("schema") != ALLOCATOR_SCHEMA:
        raise RuntimeError(f"unexpected allocator schema {allocator.get('schema')}")

    lineage = ((scoreboard.get("input_lineage") or {}).get("prospective_ledger") or {})
    if not lineage.get("sha256"):
        raise RuntimeError("scoreboard prospective-ledger lineage is required")
    lanes = {str(x.get("program_id")): x for x in (scoreboard.get("lanes") or [])}

    zero_weight: list[dict[str, Any]] = []
    for row in allocator.get("sleeve_actions") or []:
        sleeve = str(row.get("sleeve") or "")
        program = _SLEEVE_TO_PROGRAM.get(sleeve, sleeve)
        lane = lanes.get(program)
        if lane is None:
            continue
        row["source_program_id"] = program
        row["observation_status"] = lane.get("observation_status") or _observation_status(lane)
        row["observation_lineage"] = lane.get("observation_lineage") or {
            "prospective_ledger_sha256": lineage["sha256"]
        }
        if _is_zero_weight_action(row):
            zero_weight.append({
                "sleeve": sleeve,
                "source_program_id": program,
                "observation_status": row["observation_status"],
                "reason": row.get("reason"),
            })

    allocator["source_scoreboard_lineage"] = {
        "scoreboard_generated_at": scoreboard.get("generated_at"),
        "prospective_ledger": lineage,
    }
    allocator["zero_weight_lane_visibility"] = zero_weight
    allocator.setdefault("boundaries", {})["observation_status_changes_allocation_authority"] = False
    return allocator


def self_test() -> None:
    ledger = {
        "schema": LEDGER_SCHEMA,
        "generated_at": "2026-09-17T00:00:00+00:00",
        "market_data_asof": "2026-09-17",
        "cohorts": [{
            "program_id": "HOMEBUILDERS",
            "cohort_id": "HOMEBUILDERS:test",
            "status": "OPEN",
            "signal_date": "2026-09-16",
            "source_adapter_sha256": "abc",
            "source_ref": "ref",
        }],
    }
    raw = (json.dumps(ledger, sort_keys=True) + "\n").encode()
    score = {
        "schema": SCOREBOARD_SCHEMA,
        "generated_at": "2026-09-17T00:01:00+00:00",
        "lanes": [
            {"program_id": "HOMEBUILDERS", "prospective_evidence": {"ledger_status": "PRESENT"}},
            {"program_id": "P46"},
            {"program_id": "P558"},
            {"program_id": "SEMICONDUCTOR_SHARED_RIDGE", "prospective_evidence": {"ledger_status": "NOT_SUPPLIED"}},
        ],
    }
    score = annotate_scoreboard(score, ledger, raw)
    by_id = {x["program_id"]: x for x in score["lanes"]}
    assert by_id["HOMEBUILDERS"]["observation_status"] == ACTIVE
    assert by_id["P46"]["observation_status"] == CONTEXT_ONLY
    assert by_id["P558"]["observation_status"] == ACTIVE
    assert by_id["SEMICONDUCTOR_SHARED_RIDGE"]["observation_status"] == BLOCKED_NO_FROZEN_OBSERVATION_CONTRACT

    alloc = {
        "schema": ALLOCATOR_SCHEMA,
        "sleeve_actions": [
            {"sleeve": "HOMEBUILDERS", "action": "WAIT", "family_weight": 0.0, "reason": "no sizing authority"},
            {"sleeve": "P46", "action": "NO_ACTION", "target_weight": 0.0, "reason": "context only"},
            {"sleeve": "P558_KMLM_SUBSTITUTION", "action": "NO_ACTION", "target_weight": 0.0, "reason": "challenger only"},
        ],
        "boundaries": {},
    }
    alloc = annotate_allocator(score, alloc)
    statuses = {x["source_program_id"]: x["observation_status"] for x in alloc["zero_weight_lane_visibility"]}
    assert statuses == {"HOMEBUILDERS": ACTIVE, "P46": CONTEXT_ONLY, "P558": ACTIVE}
    assert alloc["source_scoreboard_lineage"]["prospective_ledger"]["sha256"]
    print("FORWARD_SCOREBOARD_LINEAGE_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--mode", choices=("scoreboard", "allocator"))
    p.add_argument("--scoreboard")
    p.add_argument("--ledger")
    p.add_argument("--allocator")
    p.add_argument("--output")
    args = p.parse_args()

    if args.self_test:
        self_test()
        return
    if not args.mode or not args.scoreboard or not args.output:
        p.error("--mode, --scoreboard and --output are required unless --self-test")

    score_path = Path(args.scoreboard)
    scoreboard, _ = _read(score_path)
    if args.mode == "scoreboard":
        if not args.ledger:
            p.error("--ledger is required in scoreboard mode")
        ledger, ledger_raw = _read(Path(args.ledger))
        result = annotate_scoreboard(scoreboard, ledger, ledger_raw)
    else:
        if not args.allocator:
            p.error("--allocator is required in allocator mode")
        allocator, _ = _read(Path(args.allocator))
        result = annotate_allocator(scoreboard, allocator)
    _write(Path(args.output), result)


if __name__ == "__main__":
    main()
