from __future__ import annotations

"""Fixed fail-closed public consumer for P04 W106 regime-1 recovery research.

Only a run-bound encrypted private source capsule is admitted. The runner reconstructs
public MNQ_DATA at the pinned commit, executes the frozen W106 producer semantics plus
the current checkpoint/recovery consumer, and emits a compact sanitized receipt.
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "p04-w106-recovery-ephemeral-x25519-v1"
HARNESS = "mm_ibkr_p04_w106_regime1_recovery_v1"
INFO = b"commandcenter-p04-w106-recovery-ephemeral-v1"
PRODUCER_SHA = "76aa7e9bb64a1aca36865076df1fa4b25f1b06a9"
MNQ_SOURCE_SHA = "fc5508e2c152938d6d9eb70a36b888ae26107176"
REQUIRED = {
    "current/scripts/research/mnq_crw_w106_checkpointed_replay_20260905.py",
    "current/scripts/research/mnq_regime1_recovery_separator_20260904.py",
    "producer/scripts/research/mnq_crw_proven_bars_rebuild_20260901.py",
    "producer/scripts/research/mnq_crw_w106_wide_event_replay_20260904.py",
    "producer/scripts/research/mnq_crw_canonical_replay_20260901.py",
    "producer/scripts/research/mnq_crw_lifecycle_replay_20260901.py",
    "producer/config/selected_runtime_universe_14tu.json",
    "producer/strategy_builder_condition_contract_14th31kn.py",
}


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _aad(run_id: str, key_id: str) -> bytes:
    return json.dumps(
        {"schema": SCHEMA, "run_id": str(run_id), "authority": "research_only", "harness": HARNESS, "recipient_key_id": key_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive(shared: bytes, aad: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(aad).digest(), info=INFO).derive(shared)


def _allowed(rel: str) -> bool:
    return (
        rel in REQUIRED
        or rel.startswith("producer/strategies/")
    )


def _extract_and_validate(payload: bytes, root: Path) -> dict:
    archive = root / "payload.tar.gz"
    archive.write_bytes(payload)
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            target = (root / member.name).resolve()
            if target != root.resolve() and root.resolve() not in target.parents:
                raise RuntimeError("unsafe P04 archive path")
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError("unsafe P04 archive member type")
        tf.extractall(root)
    archive.unlink(missing_ok=True)

    manifest_path = root / "payload-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "mm-ibkr-p04-w106-recovery-payload-v1":
        raise RuntimeError("P04 payload schema mismatch")
    if manifest.get("authority") != "research_only" or manifest.get("harness") != HARNESS:
        raise RuntimeError("P04 payload authority/harness mismatch")
    if manifest.get("producer_sha") != PRODUCER_SHA:
        raise RuntimeError("P04 frozen producer SHA mismatch")
    files = manifest.get("files") or {}
    if not REQUIRED.issubset(files):
        raise RuntimeError("P04 required private dependency missing")
    for rel, digest in files.items():
        if not _allowed(rel):
            raise RuntimeError(f"P04 payload path not admitted: {rel}")
        path = root / rel
        if not path.is_file() or _sha256(path) != digest:
            raise RuntimeError(f"P04 inner digest mismatch: {rel}")
    return manifest


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if completed.returncode != 0:
        tail = "\n".join(completed.stdout.splitlines()[-30:])
        raise RuntimeError(f"P04 fixed command failed rc={completed.returncode}: {tail}")


def _execute(root: Path) -> dict:
    producer = root / "producer"
    current = root / "current"
    work = root / "work"
    work.mkdir()
    source = work / "mnq-source"

    _run(["git", "clone", "--filter=blob:none", "--no-checkout", "https://github.com/mbytes21/MNQ_DATA.git", str(source)], cwd=root)
    _run(["git", "sparse-checkout", "init", "--no-cone"], cwd=source)
    _run(["git", "sparse-checkout", "set", "--no-cone", "plaintext_csv/MNQ */*.Last.csv"], cwd=source)
    _run(["git", "checkout", MNQ_SOURCE_SHA], cwd=source)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if head != MNQ_SOURCE_SHA:
        raise RuntimeError("P04 MNQ source checkout mismatch")

    bars = work / "mnq-crw-join-bars.csv"
    _run([
        "python", str(producer / "scripts/research/mnq_crw_proven_bars_rebuild_20260901.py"),
        "--source-root", str(source / "plaintext_csv"), "--output", str(bars),
    ], cwd=producer)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(producer)
    checkpoint = current / "scripts/research/mnq_crw_w106_checkpointed_replay_20260905.py"
    runtime = producer / "config/selected_runtime_universe_14tu.json"
    shards = work / "w106-shards"
    for index in range(4):
        out = shards / f"shard-{index}"
        _run([
            "python", str(checkpoint), "--producer-root", str(producer), "--bars", str(bars),
            "--runtime-config", str(runtime), "--shard-count", "4", "shard", "--shard-index", str(index),
            "--output-dir", str(out),
        ], cwd=root, env=env)

    combined = work / "w106"
    _run([
        "python", str(checkpoint), "--producer-root", str(producer), "--bars", str(bars),
        "--runtime-config", str(runtime), "--shard-count", "4", "combine",
        "--shards-root", str(shards), "--output-root", str(combined),
    ], cwd=root, env=env)

    w106_path = combined / "mnq-w106-wide-result.json"
    w106 = json.loads(w106_path.read_text(encoding="utf-8"))
    if w106.get("schema") != "mm.mnq_crw_w106_wide_event_replay.v1" or w106.get("accepted_screen_parity_pass") is not True:
        raise RuntimeError("P04 W106 accepted-screen parity failed")

    result_dir = work / "result"
    result_dir.mkdir()
    separator_path = result_dir / "mnq-w106-regime1-recovery-result.json"
    _run([
        "python", str(current / "scripts/research/mnq_regime1_recovery_separator_20260904.py"),
        "--bars", str(bars), "--events", str(combined / "mnq-w106-wide-dca-events.csv"), "--output", str(separator_path),
    ], cwd=root)
    separator = json.loads(separator_path.read_text(encoding="utf-8"))
    metrics = w106.get("metrics") or {}
    return {
        "schema": "p04-w106-recovery-sanitized-receipt-v1",
        "authority": "research_only",
        "harness": HARNESS,
        "producer_sha": PRODUCER_SHA,
        "mnq_source_sha": MNQ_SOURCE_SHA,
        "w106_result_sha256": _sha256(w106_path),
        "separator_result_sha256": _sha256(separator_path),
        "w106": {
            "accepted_screen_parity_pass": True,
            "closed_trades": metrics.get("closed_trades"),
            "wide_dca_fill_events": metrics.get("wide_dca_fill_events"),
            "mean_peak_deployed_fraction_closed": metrics.get("mean_peak_deployed_fraction_closed"),
            "max_drawdown_points_per_max_contract_equivalent": metrics.get("max_drawdown_points_per_max_contract_equivalent"),
        },
        "separator": {
            "events": separator.get("events"),
            "decision": separator.get("decision"),
            "aggregate": separator.get("aggregate"),
        },
    }


def consume(envelope_path: Path, private_key_path: Path, expected_run_id: str) -> dict:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    required = {"schema", "run_id", "authority", "harness", "recipient_key_id", "sender_public_b64", "nonce_b64", "ciphertext_b64", "plaintext_sha256"}
    if set(env) != required or env.get("schema") != SCHEMA or str(env.get("run_id")) != str(expected_run_id):
        raise RuntimeError("P04 envelope identity mismatch")
    if env.get("authority") != "research_only" or env.get("harness") != HARNESS:
        raise RuntimeError("P04 envelope authority/harness mismatch")

    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env.get("recipient_key_id") != key_id:
        raise RuntimeError("P04 recipient key mismatch")
    aad = _aad(expected_run_id, key_id)
    sender_raw = _b64d(env["sender_public_b64"])
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(_derive(shared, aad)).decrypt(_b64d(env["nonce_b64"]), _b64d(env["ciphertext_b64"]), aad)
    if hashlib.sha256(plaintext).hexdigest() != env.get("plaintext_sha256"):
        raise RuntimeError("P04 decrypted payload digest mismatch")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _extract_and_validate(plaintext, root)
        return _execute(root)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    receipt = consume(Path(args.envelope), Path(args.private_key), args.run_id)
    print("P04_W106_RECOVERY_RECEIPT=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
