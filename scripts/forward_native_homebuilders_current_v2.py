from __future__ import annotations

"""Narrow v2 binding for currentized Homebuilders encrypted forward compute.

Reuses the proven v1 envelope/hash/return implementation unchanged. The only added
binding is a new frozen Homebuilders source closure whose private entry point sets the
legacy data loader cutoff to the requested current as-of date before running the same
frozen scientific chain.
"""

import argparse
import json
import sys
from pathlib import Path

import scripts.forward_native_ephemeral_consumer_v1 as base

HARNESS = "homebuilders_adaptive_duration_current_v2"
SOURCE_REF = "1dffd4a4a889925e795ab214fabc4a764791bdab"
FILES = {
    "research/run_homebuilders_adaptive_duration_forward_current_20260912.py",
    "research/run_homebuilders_adaptive_duration_forward_20260905.py",
    "research/run_homebuilders_forward_observer_20260902.py",
    "research/run_industry_generic_entry_transport_20260902.py",
    "research/run_entry_cross_sector_reverse_transfer_20260902.py",
    "research/run_survivor_entry_value_20260902.py",
    "research/run_survivor_fixed10_vs20_capital_20260902.py",
    "research/homebuilders_adaptive_duration_forward_contract_20260905.json",
    "research/homebuilders_forward_observer_contract_20260902.json",
}

base.HARNESS_SPECS[HARNESS] = {
    "program_id": "HOMEBUILDERS",
    "source_ref": SOURCE_REF,
    "files": FILES,
}
_ORIGINAL_EXECUTE = base._execute


def _execute(root: Path, harness: str, adapter_script: Path):
    if harness != HARNESS:
        return _ORIGINAL_EXECUTE(root, harness, adapter_script)
    spec = base.HARNESS_SPECS[harness]
    adapter = root / "artifacts" / f"forward_program_adapter_{spec['program_id'].lower()}.json"
    adapter.parent.mkdir(parents=True, exist_ok=True)
    native = root / "research/results/homebuilders_adaptive_duration_forward_current.json"
    native.parent.mkdir(parents=True, exist_ok=True)
    base._run(
        [
            sys.executable,
            "-m",
            "research.run_homebuilders_adaptive_duration_forward_current_20260912",
            "--output",
            str(native.relative_to(root)),
        ],
        root,
    )
    payload = json.loads(native.read_text(encoding="utf-8"))
    current = payload.get("currentization") or {}
    if current.get("scientific_model_changed") is not False:
        raise RuntimeError("Homebuilders v2 currentization boundary missing")
    if int(current.get("stale_calendar_days", 999)) > int(current.get("max_allowed_stale_calendar_days", -1)):
        raise RuntimeError("Homebuilders v2 result exceeded currentization freshness gate")
    base._run(
        [
            sys.executable,
            str(adapter_script),
            "--program",
            "HOMEBUILDERS",
            "--input",
            str(native),
            "--output",
            str(adapter),
        ],
        root,
    )
    return native, None, adapter


base._execute = _execute


def self_test() -> None:
    spec = base.HARNESS_SPECS[HARNESS]
    assert spec["program_id"] == "HOMEBUILDERS"
    assert spec["source_ref"] == SOURCE_REF
    assert "research/run_homebuilders_adaptive_duration_forward_current_20260912.py" in spec["files"]
    assert "research/run_homebuilders_adaptive_duration_forward_20260905.py" in spec["files"]
    print("FORWARD_NATIVE_HOMEBUILDERS_CURRENT_V2_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope")
    p.add_argument("--private-key")
    p.add_argument("--run-id")
    p.add_argument("--harness", default=HARNESS)
    p.add_argument("--adapter-script", default="research/forward_native_program_adapter_r1.py")
    p.add_argument("--return-envelope")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if args.harness != HARNESS:
        raise RuntimeError(f"unexpected harness {args.harness}")
    if not all((args.envelope, args.private_key, args.run_id, args.return_envelope)):
        p.error("live consume requires envelope, private-key, run-id and return-envelope")
    receipt = base.consume(
        Path(args.envelope),
        Path(args.private_key),
        args.run_id,
        HARNESS,
        Path(args.adapter_script).resolve(),
        Path(args.return_envelope),
    )
    print("FORWARD_NATIVE_PUBLIC_RECEIPT=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
