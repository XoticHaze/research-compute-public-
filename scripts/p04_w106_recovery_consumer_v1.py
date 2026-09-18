from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

SCHEMA = "p04-w106-recovery-ephemeral-x25519-v1"
HARNESS = "mm_ibkr_p04_w106_regime1_recovery_v1"
PAYLOAD_SCHEMA = "mm-ibkr-p04-w106-recovery-payload-v1"
PRODUCER_SHA = "76aa7e9bb64a1aca36865076df1fa4b25f1b06a9"
MNQ_SOURCE_SHA = "fc5508e2c152938d6d9eb70a36b888ae26107176"
SHARD_COUNT = 4


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("EXEC=" + json.dumps(cmd))
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def safe_extract_targz(raw: bytes, root: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        root_resolved = root.resolve()
        for member in tf.getmembers():
            target = (root / member.name).resolve()
            if root_resolved not in target.parents and target != root_resolved:
                raise SystemExit("payload archive path traversal rejected")
            if member.issym() or member.islnk():
                raise SystemExit("payload archive links rejected")
        tf.extractall(root)


def verify_manifest(root: Path) -> dict[str, object]:
    manifest_path = root / "payload-manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("missing payload manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != PAYLOAD_SCHEMA:
        raise SystemExit("payload schema mismatch")
    if manifest.get("authority") != "research_only":
        raise SystemExit("payload authority mismatch")
    if manifest.get("harness") != HARNESS:
        raise SystemExit("payload harness mismatch")
    if manifest.get("producer_sha") != PRODUCER_SHA:
        raise SystemExit("producer pin mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise SystemExit("payload file manifest missing")
    allowed_prefixes = ("current/", "producer/")
    discovered: dict[str, str] = {}
    for prefix in (root / "current", root / "producer"):
        if not prefix.is_dir():
            raise SystemExit(f"missing payload directory: {prefix.name}")
        for path in sorted(p for p in prefix.rglob("*") if p.is_file()):
            rel = path.relative_to(root).as_posix()
            if not rel.startswith(allowed_prefixes):
                raise SystemExit("unexpected payload file path")
            discovered[rel] = sha256_file(path)
    if discovered != files:
        missing = sorted(set(files) - set(discovered))
        extra = sorted(set(discovered) - set(files))
        mismatch = sorted(k for k in set(files) & set(discovered) if files[k] != discovered[k])
        raise SystemExit(f"payload identity mismatch missing={missing} extra={extra} mismatch={mismatch}")
    return manifest


def acquire_mnq_source(root: Path) -> Path:
    source = root / "mnq-source"
    run(["git", "clone", "--filter=blob:none", "--no-checkout", "https://github.com/mbytes21/MNQ_DATA.git", str(source)])
    run(["git", "sparse-checkout", "init", "--no-cone"], cwd=source)
    run(["git", "sparse-checkout", "set", "--no-cone", "plaintext_csv/MNQ */*.Last.csv"], cwd=source)
    run(["git", "checkout", MNQ_SOURCE_SHA], cwd=source)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if head != MNQ_SOURCE_SHA:
        raise SystemExit("MNQ source pin mismatch")
    return source / "plaintext_csv"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--ciphertext", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--response-root", required=True)
    a = p.parse_args()

    env_node = json.loads(Path(a.envelope).read_text(encoding="utf-8"))
    plaintext = decrypt_assembled_ciphertext(
        envelope=env_node,
        ciphertext=Path(a.ciphertext).read_bytes(),
        private_key_path=Path(a.private_key),
        expected_schema=SCHEMA,
        expected_run_id=a.run_id,
        expected_harness=HARNESS,
        response_root=a.response_root,
    )

    with tempfile.TemporaryDirectory(prefix="p04-w106-") as td:
        root = Path(td)
        payload = root / "payload"
        payload.mkdir()
        safe_extract_targz(plaintext, payload)
        manifest = verify_manifest(payload)
        current = payload / "current"
        producer = payload / "producer"

        required = [
            current / "scripts/research/mnq_crw_w106_checkpointed_replay_20260905.py",
            current / "scripts/research/mnq_regime1_recovery_separator_20260904.py",
            producer / "scripts/research/mnq_crw_proven_bars_rebuild_20260901.py",
            producer / "config/selected_runtime_universe_14tu.json",
        ]
        for path in required:
            if not path.is_file():
                raise SystemExit(f"required payload dependency missing: {path.relative_to(payload)}")

        source_root = acquire_mnq_source(root)
        bars = root / "mnq-crw-join-bars.csv"
        replay_root = root / "w106"
        shards_root = root / "shards"
        separator_out = root / "separator.json"

        py_env = os.environ.copy()
        py_env["PYTHONPATH"] = str(producer)
        run([
            "python",
            str(producer / "scripts/research/mnq_crw_proven_bars_rebuild_20260901.py"),
            "--source-root", str(source_root),
            "--output", str(bars),
        ], env=py_env)
        if not bars.is_file() or bars.stat().st_size == 0:
            raise SystemExit("admitted MNQ bars were not materialized")

        checkpoint = current / "scripts/research/mnq_crw_w106_checkpointed_replay_20260905.py"
        runtime = producer / "config/selected_runtime_universe_14tu.json"
        for i in range(SHARD_COUNT):
            run([
                "python", str(checkpoint),
                "--producer-root", str(producer),
                "--bars", str(bars),
                "--runtime-config", str(runtime),
                "--shard-count", str(SHARD_COUNT),
                "shard", "--shard-index", str(i),
                "--output-dir", str(shards_root / f"shard-{i}"),
            ], env=py_env)
        run([
            "python", str(checkpoint),
            "--producer-root", str(producer),
            "--bars", str(bars),
            "--runtime-config", str(runtime),
            "--shard-count", str(SHARD_COUNT),
            "combine", "--shards-root", str(shards_root),
            "--output-root", str(replay_root),
        ], env=py_env)

        w106 = json.loads((replay_root / "mnq-w106-wide-result.json").read_text(encoding="utf-8"))
        if w106.get("accepted_screen_parity_pass") is not True:
            raise SystemExit("W106 accepted-screen parity failed")
        events_path = replay_root / "mnq-w106-wide-dca-events.csv"
        run([
            "python",
            str(current / "scripts/research/mnq_regime1_recovery_separator_20260904.py"),
            "--bars", str(bars),
            "--events", str(events_path),
            "--output", str(separator_out),
        ], env=py_env)
        separator = json.loads(separator_out.read_text(encoding="utf-8"))

        receipt = {
            "schema": "p04-w106-recovery-sanitized-receipt-v1",
            "authority": "research_only",
            "run_id": str(a.run_id),
            "harness": HARNESS,
            "private_payload_head": manifest.get("current_head"),
            "producer_sha": PRODUCER_SHA,
            "mnq_source_sha": MNQ_SOURCE_SHA,
            "payload_plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
            "bars_sha256": sha256_file(bars),
            "accepted_screen_parity_pass": True,
            "w106_closed_trades": int((w106.get("metrics") or {}).get("closed_trades", 0)),
            "w106_wide_dca_fill_events": int((w106.get("metrics") or {}).get("wide_dca_fill_events", 0)),
            "w106_net_points_per_max_contract_equivalent": (w106.get("metrics") or {}).get("net_points_per_max_contract_equivalent"),
            "w106_max_drawdown_points_per_max_contract_equivalent": (w106.get("metrics") or {}).get("max_drawdown_points_per_max_contract_equivalent"),
            "separator_events": separator.get("events"),
            "separator_folds": separator.get("folds"),
            "separator_aggregate": separator.get("aggregate"),
            "decision": separator.get("decision"),
            "strategy_spec_write": False,
            "runtime_activation": False,
            "broker_submit": False,
            "promotion_authority": False,
            "live_trading_change": False,
        }
        print("P04_W106_RECOVERY_RECEIPT=" + json.dumps(receipt, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
