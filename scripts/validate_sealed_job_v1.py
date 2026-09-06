from __future__ import annotations

"""Fail-closed validator/executor boundary for sealed research jobs."""

import argparse
import hashlib
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path

FORBIDDEN = {"payload", "plaintext", "command", "shell", "script", "promotion", "runtime", "trading"}
ALLOWED_TOP = {"schema_version", "job_id", "mode", "authority", "ciphertext", "encryption", "harness"}
ALLOWED_HARNESS = {"deterministic_sum_v1", "research_foundry_pr285_stage1_v1"}
PR285_FILES = {
    "payload-manifest.json",
    "research/industry_relative_value_stage1_20260905.py",
    "research/energy_ep_relative_value_stage1_contract_20260905.json",
    "research/aerospace_defense_relative_value_stage1_contract_20260905.json",
    "research/industry_component_stage1_mechanical.py",
    "tests/test_industry_relative_value_stage1_contracts_20260905.py",
}


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


def _safe_extract(tf: tarfile.TarFile, root: Path) -> None:
    names = set(tf.getnames())
    if names != PR285_FILES:
        raise RuntimeError(f"PR285 payload file set mismatch: {sorted(names)}")
    for member in tf.getmembers():
        target = (root / member.name).resolve()
        if root.resolve() not in target.parents and target != root.resolve():
            raise RuntimeError("archive path traversal rejected")
        if not member.isfile():
            raise RuntimeError("non-file archive member rejected")
    tf.extractall(root)


def run_pr285(payload_path: Path) -> dict:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        with tarfile.open(payload_path, "r:gz") as tf:
            _safe_extract(tf, root)
        pm = json.loads((root / "payload-manifest.json").read_text(encoding="utf-8"))
        if pm.get("schema") != "research-foundry-pr285-stage1-payload-v1" or pm.get("harness") != "research_foundry_pr285_stage1_v1":
            raise RuntimeError("PR285 payload manifest identity mismatch")
        expected = pm.get("files") or {}
        if set(expected) != PR285_FILES - {"payload-manifest.json"}:
            raise RuntimeError("PR285 manifest file set mismatch")
        for rel, digest in expected.items():
            if sha256(root / rel) != digest:
                raise RuntimeError(f"PR285 inner digest mismatch: {rel}")
        subprocess.run(["python", "-m", "py_compile", "research/industry_relative_value_stage1_20260905.py"], cwd=root, check=True)
        subprocess.run(["python", "-m", "pytest", "-q", "tests/test_industry_relative_value_stage1_contracts_20260905.py"], cwd=root, check=True)
        results = {}
        for family, contract in {
            "energy_ep": "research/energy_ep_relative_value_stage1_contract_20260905.json",
            "aerospace_defense": "research/aerospace_defense_relative_value_stage1_contract_20260905.json",
        }.items():
            out = root / f"{family}.json"
            subprocess.run([
                "python", "-m", "research.industry_relative_value_stage1_20260905",
                "--contract", contract, "--output", str(out)
            ], cwd=root, check=True)
            r = json.loads(out.read_text(encoding="utf-8"))
            if r.get("family") != family or r.get("external_holdouts", {}).get("loaded") is not False:
                raise RuntimeError(f"PR285 result boundary failed: {family}")
            results[family] = {
                "classification": r.get("classification"),
                "external_holdouts_loaded": False,
                "result_sha256": sha256(out),
                "result": r,
            }
        return {"harness": "research_foundry_pr285_stage1_v1", "families": results}


def run_fixed_harness(harness: str, payload_path: Path) -> dict:
    if harness == "deterministic_sum_v1":
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        if set(payload) != {"schema", "values"} or payload["schema"] != "sealed-fixture-v1":
            raise RuntimeError("decrypted payload schema invalid")
        values = payload["values"]
        if not isinstance(values, list) or not values or any(type(x) not in (int, float) for x in values):
            raise RuntimeError("fixture values invalid")
        return {"harness": harness, "count": len(values), "sum": float(sum(values))}
    if harness == "research_foundry_pr285_stage1_v1":
        return run_pr285(payload_path)
    raise RuntimeError("harness not implemented")


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
