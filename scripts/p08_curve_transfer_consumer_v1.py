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

SCHEMA = "p08-curve-transfer-ephemeral-x25519-v1"
HARNESS = "p08_curve_state_transfer_v1"
AUTHORITY = "research_only"
EXPECTED_HEAD = "0cb9a5bd944226ad3ca7eed83dbfff8525f18056"
EXPECTED_RUNNER_BLOB = "47a3576834804a274450f6b97a95b0fb5005578a"
EXPECTED_CURVE_BLOB = "44f92960fe11656928848b4c0a7ec57c5901755f"


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def _decode_source(node: dict, key: str, expected_blob: str) -> bytes:
    raw = base64.b64decode(str(node[key]).encode("ascii"), validate=True)
    actual = git_blob_sha(raw)
    if actual != expected_blob:
        raise RuntimeError(f"{key} git blob mismatch: {actual}")
    return raw


def _sanitize(result: dict) -> dict:
    if result.get("schema") != "foundry.research.curve_state_transfer.v1":
        raise RuntimeError("unexpected P08 result schema")
    bands = {}
    for name, row in (result.get("bands") or {}).items():
        dev = ((row.get("development") or {}).get("comparison") or {})
        external = {}
        for group_name, group in (row.get("external") or {}).items():
            comp = group.get("comparison") or {}
            external[group_name] = {
                "status": group.get("status"),
                "supported_symbols": group.get("supported_symbols") or [],
                "external_improved_horizons": group.get("external_improved_horizons"),
                "external_group_pass": group.get("external_group_pass"),
                "horizons": {
                    h: {
                        "median_quantitative_ratio": v.get("median_quantitative_ratio"),
                        "continuation_accuracy_delta": v.get("continuation_accuracy_delta"),
                    }
                    for h, v in (comp.get("horizons") or {}).items()
                },
            }
        bands[name] = {
            "windows": row.get("windows"),
            "development_pass": dev.get("development_pass"),
            "development_improved_horizons": dev.get("improved_horizons"),
            "development_worst_horizon_median_ratio": dev.get("worst_horizon_median_ratio"),
            "development_horizons": {
                h: {
                    "median_quantitative_ratio": v.get("median_quantitative_ratio"),
                    "continuation_accuracy_delta": v.get("continuation_accuracy_delta"),
                }
                for h, v in (dev.get("horizons") or {}).items()
            },
            "supported_external_groups": row.get("supported_external_groups"),
            "passing_external_groups": row.get("passing_external_groups"),
            "broad_transfer_pass": row.get("broad_transfer_pass"),
            "external": external,
        }
    return {
        "schema": "p08-curve-state-transfer-receipt-v1",
        "authority": AUTHORITY,
        "source_head": EXPECTED_HEAD,
        "runner_blob_sha": EXPECTED_RUNNER_BLOB,
        "curve_state_blob_sha": EXPECTED_CURVE_BLOB,
        "classification": result.get("classification"),
        "development_survivors": result.get("development_survivors") or [],
        "transfer_survivors": result.get("transfer_survivors") or [],
        "source_error_symbols": sorted((result.get("source_errors") or {}).keys()),
        "bands": bands,
        "strategy_spec_write": False,
        "runtime_activation": False,
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
        raise RuntimeError("P08 payload field set mismatch")
    if node["schema"] != "p08-curve-transfer-private-payload-v1" or node["authority"] != AUTHORITY:
        raise RuntimeError("P08 payload schema/authority mismatch")
    if node["source_head"] != EXPECTED_HEAD:
        raise RuntimeError("P08 source head mismatch")
    if node["runner_blob_sha"] != EXPECTED_RUNNER_BLOB or node["curve_state_blob_sha"] != EXPECTED_CURVE_BLOB:
        raise RuntimeError("P08 declared blob identity mismatch")

    runner = _decode_source(node, "runner_source_b64", EXPECTED_RUNNER_BLOB)
    curve = _decode_source(node, "curve_state_source_b64", EXPECTED_CURVE_BLOB)

    with tempfile.TemporaryDirectory(prefix="p08-curve-") as td:
        root = Path(td)
        (root / "foundry_mm_ml").mkdir()
        (root / "research").mkdir()
        (root / "foundry_mm_ml" / "__init__.py").write_text("", encoding="utf-8")
        (root / "research" / "__init__.py").write_text("", encoding="utf-8")
        (root / "foundry_mm_ml" / "curve_state.py").write_bytes(curve)
        (root / "research" / "run_curve_state_transfer_20260904.py").write_bytes(runner)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(root)
        proc = subprocess.run(
            ["python", "-m", "research.run_curve_state_transfer_20260904"],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            timeout=1800,
            check=False,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout)[-1600:]
            raise RuntimeError(f"P08 frozen experiment failed rc={proc.returncode}: {tail}")
        result_path = root / "research" / "results" / "curve_state_transfer_20260904.json"
        if not result_path.exists():
            raise RuntimeError("P08 result artifact missing")
        result = json.loads(result_path.read_text(encoding="utf-8"))

    print("P08_CURVE_TRANSFER_RECEIPT=" + json.dumps(_sanitize(result), sort_keys=True))


if __name__ == "__main__":
    main()
