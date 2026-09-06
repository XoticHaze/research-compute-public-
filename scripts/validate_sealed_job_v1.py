from __future__ import annotations

"""Fail-closed validator/executor boundary for sealed research jobs.

This validator never executes arbitrary commands from a manifest. It validates only the
envelope and dispatches a fixed local harness identifier after decryption has occurred in
a separately controlled step. The synthetic CI proof uses an ephemeral key and harmless
fixture; it proves transport mechanics only, not private integration authority.
"""

import argparse
import hashlib
import json
from pathlib import Path

FORBIDDEN = {"payload", "plaintext", "command", "shell", "script", "promotion", "runtime", "trading"}
ALLOWED_TOP = {"schema_version", "job_id", "mode", "authority", "ciphertext", "encryption", "harness"}
ALLOWED_HARNESS = {"deterministic_sum_v1"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_manifest(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise RuntimeError("manifest must be object")
    unexpected = set(obj) - ALLOWED_TOP
    if unexpected:
        raise RuntimeError(f"unexpected manifest fields={sorted(unexpected)}")
    if FORBIDDEN.intersection(obj):
        raise RuntimeError("plaintext/execution authority fields forbidden")
    if obj.get("schema_version") != "sealed-job-v1":
        raise RuntimeError("schema_version must be sealed-job-v1")
    if obj.get("mode") != "sealed":
        raise RuntimeError("mode must be sealed")
    if obj.get("authority") != "research_only":
        raise RuntimeError("authority must be research_only")
    if obj.get("harness") not in ALLOWED_HARNESS:
        raise RuntimeError("unapproved fixed harness")
    cipher = obj.get("ciphertext")
    if not isinstance(cipher, dict) or set(cipher) != {"path", "sha256"}:
        raise RuntimeError("ciphertext must contain only path/sha256")
    enc = obj.get("encryption")
    if not isinstance(enc, dict) or set(enc) != {"algorithm", "recipient_key_id"}:
        raise RuntimeError("encryption must contain only algorithm/recipient_key_id")
    if enc["algorithm"] != "age-x25519":
        raise RuntimeError("only age-x25519 accepted")
    cp = Path(cipher["path"])
    if not cp.is_file():
        raise RuntimeError("ciphertext file missing")
    actual = sha256(cp)
    if actual != cipher["sha256"]:
        raise RuntimeError(f"ciphertext digest mismatch expected={cipher['sha256']} actual={actual}")
    if not enc["recipient_key_id"].startswith("sha256:"):
        raise RuntimeError("recipient_key_id must be sha256 fingerprint")
    return obj


def run_fixed_harness(harness: str, payload_path: Path) -> dict:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    if harness != "deterministic_sum_v1":
        raise RuntimeError("harness not implemented")
    if set(payload) != {"schema", "values"} or payload["schema"] != "sealed-fixture-v1":
        raise RuntimeError("decrypted payload schema invalid")
    values = payload["values"]
    if not isinstance(values, list) or not values or any(type(x) not in (int, float) for x in values):
        raise RuntimeError("fixture values invalid")
    return {"harness": harness, "count": len(values), "sum": float(sum(values))}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("manifest")
    p.add_argument("--decrypted")
    args = p.parse_args()
    manifest = validate_manifest(Path(args.manifest))
    result = {"manifest_status": "PASS", "job_id": manifest["job_id"], "authority": manifest["authority"]}
    if args.decrypted:
        result["harness_result"] = run_fixed_harness(manifest["harness"], Path(args.decrypted))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
