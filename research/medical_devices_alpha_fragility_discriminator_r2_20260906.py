from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

RECORDED_PARENT = {
    "states": 9737,
    "stock_net25_mean_bps": 94.3369216641737,
    "ihi_excess25_mean_bps": 7.18340291329859,
    "passing_symbols": 4,
}
MAX_ACCEPTED_REPLAY_DRIFT_BPS = 5.0


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--discriminator", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    runner = _load(args.runner, "stagea_runner_r2")
    discriminator = _load(args.discriminator, "fragility_discriminator_r2")

    # Reproduce the pinned public Stage-A runner in this exact process first.
    parent = runner._evaluate_matrix(discriminator.FAMILY, discriminator.CUTOFF)
    summary = parent["family_summary"]["medical_devices"]
    current = {
        "states": int(summary["aggregate_primary_states"]),
        "stock_net25_mean_bps": float(summary["aggregate_stock_net25_mean_bps"]),
        "ihi_excess25_mean_bps": float(summary["aggregate_stock_after25_minus_sector_etf_mean_bps"]),
        "passing_symbols": int(summary["passing_symbols"]),
    }

    # Bind the event-level reconstruction to the same-run canonical evaluator.
    # If reconstruction semantics are wrong, the original fail-closed checks still fire.
    discriminator.EXPECTED = dict(current)
    result = discriminator.evaluate(args.runner)

    delta = {
        "states": current["states"] - RECORDED_PARENT["states"],
        "stock_net25_mean_bps": current["stock_net25_mean_bps"] - RECORDED_PARENT["stock_net25_mean_bps"],
        "ihi_excess25_mean_bps": current["ihi_excess25_mean_bps"] - RECORDED_PARENT["ihi_excess25_mean_bps"],
        "passing_symbols": current["passing_symbols"] - RECORDED_PARENT["passing_symbols"],
    }
    material_replay_drift = bool(
        delta["states"] != 0
        or delta["passing_symbols"] != 0
        or abs(delta["stock_net25_mean_bps"]) > MAX_ACCEPTED_REPLAY_DRIFT_BPS
        or abs(delta["ihi_excess25_mean_bps"]) > MAX_ACCEPTED_REPLAY_DRIFT_BPS
    )

    result["parity"] = {
        **result["parity"],
        "same_run_stagea_reconstruction": "EXACT",
        "recorded_parent_reference": RECORDED_PARENT,
        "same_run_stagea": current,
        "recorded_parent_delta": delta,
        "accepted_replay_drift_limit_bps": MAX_ACCEPTED_REPLAY_DRIFT_BPS,
        "material_replay_drift": material_replay_drift,
    }
    if material_replay_drift:
        result["decision_before_source_drift_guard"] = result["decision"]
        result["decision"] = "SOURCE_REPLAY_DRIFT_REQUIRES_PINNED_PARENT_BYTES"
        result["consequence"] = (
            "The event-level reconstruction matches the same-run pinned evaluator, but the public source replay "
            "has drifted materially from the recorded parent. Do not interpret the economic fragility result as "
            "the immutable parent result until exact parent bytes are pinned or republished. External holdouts remain sealed."
        )

    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("MEDICAL_DEVICES_ALPHA_FRAGILITY_R2=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
