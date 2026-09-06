from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

SCHEMA = "p08-swing-alpha-homebuilders-ephemeral-x25519-v1"
HARNESS = "p08_swing_alpha_homebuilders_v1"
AUTHORITY = "research_only"
EXPECTED_HEAD = "536fffa30aaadcdd36a401cbaedc6348ec8e352c"
EXPECTED_RUNNER_BLOB = "47fbcdd5cc2b82bc7d618d1cc3a8f03d26ec0703"
EXPECTED_CURVE_BLOB = "44f92960fe11656928848b4c0a7ec57c5901755f"


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def decode_source(node: dict, key: str, expected: str) -> bytes:
    raw = base64.b64decode(str(node[key]).encode("ascii"), validate=True)
    actual = git_blob_sha(raw)
    if actual != expected:
        raise RuntimeError(f"{key} git blob mismatch: {actual}")
    return raw


def sanitize(result: dict) -> dict:
    if result.get("schema") != "foundry.research.p08_swing_alpha_homebuilders.v1":
        raise RuntimeError("unexpected P08 swing-alpha result schema")
    allowed_econ = {
        "cost_bps", "events", "full_curve_bps", "return_vol_selector_bps",
        "equal_weight_homebuilders_bps", "itb_bps", "spy_bps", "qqq_bps",
        "excess_vs_return_vol_bps", "excess_vs_equal_weight_bps",
        "excess_vs_itb_bps", "excess_vs_spy_bps", "excess_vs_qqq_bps",
        "folds", "positive_fold_counts",
    }
    def econ(name: str) -> dict:
        row = result.get(name) or {}
        return {k: row.get(k) for k in allowed_econ}
    return {
        "schema": "p08-swing-alpha-homebuilders-receipt-v1",
        "authority": AUTHORITY,
        "source_head": EXPECTED_HEAD,
        "runner_blob_sha": EXPECTED_RUNNER_BLOB,
        "curve_state_blob_sha": EXPECTED_CURVE_BLOB,
        "representation": result.get("representation"),
        "baseline": result.get("baseline"),
        "consumer": result.get("consumer"),
        "homebuilders": result.get("homebuilders"),
        "matched_benchmarks": result.get("matched_benchmarks"),
        "query_start": result.get("query_start"),
        "events": result.get("events"),
        "primary": econ("primary"),
        "stress": econ("stress"),
        "decision": result.get("decision"),
        "broad_market_context_rule": result.get("broad_market_context_rule"),
        "strategy_spec_write": False,
        "runtime_activation": False,
        "capital_allocation_authority": False,
        "broker_submit": False,
        "promotion_authority": False,
        "live_trading_change": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--ciphertext", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--response-root", required=True)
    args = p.parse_args()

    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    raw = decrypt_assembled_ciphertext(
        envelope=envelope,
        ciphertext=Path(args.ciphertext).read_bytes(),
        private_key_path=Path(args.private_key),
        expected_schema=SCHEMA,
        expected_run_id=args.run_id,
        expected_harness=HARNESS,
        response_root=args.response_root,
    )
    node = json.loads(raw.decode("utf-8"))
    expected_fields = {
        "schema", "authority", "source_head", "runner_blob_sha", "curve_state_blob_sha",
        "runner_source_b64", "curve_state_source_b64",
    }
    if not isinstance(node, dict) or set(node) != expected_fields:
        raise RuntimeError("P08 swing-alpha payload field set mismatch")
    if node["schema"] != "p08-swing-alpha-homebuilders-private-payload-v1" or node["authority"] != AUTHORITY:
        raise RuntimeError("P08 swing-alpha payload schema/authority mismatch")
    if node["source_head"] != EXPECTED_HEAD:
        raise RuntimeError("P08 swing-alpha source head mismatch")
    if node["runner_blob_sha"] != EXPECTED_RUNNER_BLOB or node["curve_state_blob_sha"] != EXPECTED_CURVE_BLOB:
        raise RuntimeError("P08 swing-alpha declared blob identity mismatch")

    runner = decode_source(node, "runner_source_b64", EXPECTED_RUNNER_BLOB)
    curve = decode_source(node, "curve_state_source_b64", EXPECTED_CURVE_BLOB)
    with tempfile.TemporaryDirectory(prefix="p08-swing-alpha-") as td:
        root = Path(td)
        (root / "foundry_mm_ml").mkdir()
        (root / "research").mkdir()
        (root / "foundry_mm_ml" / "__init__.py").write_text("", encoding="utf-8")
        (root / "research" / "__init__.py").write_text("", encoding="utf-8")
        (root / "foundry_mm_ml" / "curve_state.py").write_bytes(curve)
        (root / "research" / "run_p08_swing_alpha_homebuilders_20260906.py").write_bytes(runner)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(root)
        proc = subprocess.run(
            ["python", "-m", "research.run_p08_swing_alpha_homebuilders_20260906"],
            cwd=root, env=env, text=True, capture_output=True, timeout=1800, check=False,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout)[-1800:]
            raise RuntimeError(f"P08 swing-alpha experiment failed rc={proc.returncode}: {tail}")
        result_path = root / "research" / "results" / "p08_swing_alpha_homebuilders_20260906.json"
        if not result_path.exists():
            raise RuntimeError("P08 swing-alpha result artifact missing")
        result = json.loads(result_path.read_text(encoding="utf-8"))
    print("P08_SWING_ALPHA_RECEIPT=" + json.dumps(sanitize(result), sort_keys=True))


if __name__ == "__main__":
    main()
