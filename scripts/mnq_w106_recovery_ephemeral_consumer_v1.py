from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "mnq-w106-recovery-x25519-v1"
HARNESS = "mnq_w106_regime1_recovery_v1"
INFO = b"commandcenter-mnq-w106-recovery-v1"
PRODUCER_SOURCE_COMMIT = "76aa7e9bb64a1aca36865076df1fa4b25f1b06a9"
MNQ_DATA_COMMIT = "fc5508e2c152938d6d9eb70a36b888ae26107176"
ALLOWED_FILES = {
    "manifest.json",
    "scripts/research/mnq_crw_proven_bars_rebuild_20260901.py",
    "scripts/research/mnq_crw_canonical_replay_20260901.py",
    "scripts/research/mnq_crw_lifecycle_replay_20260901.py",
    "scripts/research/mnq_crw_w106_wide_event_replay_20260904.py",
    "scripts/research/mnq_regime1_recovery_separator_20260904.py",
    "strategies/python/base.py",
    "strategies/python/crw_score_multi_mode.py",
    "strategies/features/crw_dca_contract.py",
    "strategies/features/crw_dca_feature_config.py",
    "strategies/features/crw_pine.py",
    "strategy_builder_condition_contract_14th31kn.py",
    "feature_contract.py",
    "indicators_registry.py",
    "config/selected_runtime_universe_14tu.json",
}

def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)

def aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps({"schema":SCHEMA,"run_id":str(run_id),"authority":"research_only","harness":HARNESS,"recipient_key_id":recipient_key_id},sort_keys=True,separators=(",",":")).encode()

def derive(shared: bytes, data: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(),length=32,salt=hashlib.sha256(data).digest(),info=INFO).derive(shared)

def validate_payload(plaintext: bytes) -> dict:
    with tarfile.open(fileobj=io.BytesIO(plaintext),mode="r:gz") as tf:
        names={m.name for m in tf.getmembers() if m.isfile()}
        if names!=ALLOWED_FILES: raise RuntimeError(f"payload file set mismatch: {sorted(names ^ ALLOWED_FILES)}")
        for member in tf.getmembers():
            p=Path(member.name)
            if member.isdir(): continue
            if member.issym() or member.islnk() or p.is_absolute() or ".." in p.parts: raise RuntimeError("unsafe payload member")
        f=tf.extractfile("manifest.json")
        if f is None: raise RuntimeError("manifest missing")
        manifest=json.loads(f.read())
    required={"schema","harness","authority","producer_source_commit","separator_source_commit","files_sha256"}
    if set(manifest)!=required: raise RuntimeError("manifest field set mismatch")
    if manifest["schema"]!="mnq-w106-recovery-payload-v1" or manifest["harness"]!=HARNESS or manifest["authority"]!="research_only": raise RuntimeError("manifest identity mismatch")
    if manifest["producer_source_commit"]!=PRODUCER_SOURCE_COMMIT: raise RuntimeError("producer source commit mismatch")
    if not str(manifest["separator_source_commit"]): raise RuntimeError("separator source commit missing")
    if set(manifest["files_sha256"])!=(ALLOWED_FILES-{"manifest.json"}): raise RuntimeError("manifest file digest set mismatch")
    return manifest

def run_checked(argv: list[str], cwd: Path) -> None:
    proc=subprocess.run(argv,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    print(proc.stdout[-20000:])
    if proc.returncode: raise RuntimeError(f"command failed {proc.returncode}: {' '.join(argv)}")

def consume(envelope: Path, private_key_path: Path, run_id: str) -> dict:
    env=json.loads(envelope.read_text())
    required={"schema","run_id","authority","harness","recipient_key_id","sender_public_b64","nonce_b64","ciphertext_b64","plaintext_sha256"}
    if set(env)!=required or env["schema"]!=SCHEMA or str(env["run_id"])!=str(run_id) or env["harness"]!=HARNESS or env["authority"]!="research_only": raise RuntimeError("envelope identity mismatch")
    private=x25519.X25519PrivateKey.from_private_bytes(b64d(private_key_path.read_text().strip()))
    recipient_raw=private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    key_id="sha256:"+hashlib.sha256(recipient_raw).hexdigest()
    if env["recipient_key_id"]!=key_id: raise RuntimeError("recipient fingerprint mismatch")
    data=aad(run_id,key_id)
    shared=private.exchange(x25519.X25519PublicKey.from_public_bytes(b64d(env["sender_public_b64"])))
    plaintext=ChaCha20Poly1305(derive(shared,data)).decrypt(b64d(env["nonce_b64"]),b64d(env["ciphertext_b64"]),data)
    if hashlib.sha256(plaintext).hexdigest()!=env["plaintext_sha256"]: raise RuntimeError("plaintext digest mismatch")
    manifest=validate_payload(plaintext)
    with tempfile.TemporaryDirectory(prefix="mnq-w106-recovery-") as td:
        root=Path(td)
        with tarfile.open(fileobj=io.BytesIO(plaintext),mode="r:gz") as tf: tf.extractall(root)
        for rel,expected in manifest["files_sha256"].items():
            if hashlib.sha256((root/rel).read_bytes()).hexdigest()!=expected: raise RuntimeError(f"private source digest mismatch: {rel}")
        for pkg in ["scripts","scripts/research","strategies","strategies/python","strategies/features"]:
            p=root/pkg/"__init__.py"; p.parent.mkdir(parents=True,exist_ok=True)
            if not p.exists(): p.write_text("")
        data_root=root/"mnq-data"
        run_checked(["git","clone","--filter=blob:none","https://github.com/mbytes21/MNQ_DATA.git",str(data_root)],root)
        run_checked(["git","checkout",MNQ_DATA_COMMIT],data_root)
        source_root=data_root/"plaintext_csv"
        if not source_root.is_dir(): raise RuntimeError("pinned MNQ plaintext_csv source root missing")
        bars=root/"mnq-12min.csv"; out=root/"w106"; separator=root/"separator.json"
        run_checked(["python","scripts/research/mnq_crw_proven_bars_rebuild_20260901.py","--source-root",str(source_root),"--output",str(bars)],root)
        run_checked(["python","scripts/research/mnq_crw_w106_wide_event_replay_20260904.py","--bars",str(bars),"--runtime-config","config/selected_runtime_universe_14tu.json","--output-root",str(out)],root)
        replay=json.loads((out/"mnq-w106-wide-result.json").read_text())
        if not replay.get("accepted_screen_parity_pass"): raise RuntimeError("accepted W106 screen parity failed")
        run_checked(["python","scripts/research/mnq_regime1_recovery_separator_20260904.py","--bars",str(bars),"--events",str(out/"mnq-w106-wide-dca-events.csv"),"--output",str(separator)],root)
        sep=json.loads(separator.read_text())
        return {"schema":"mnq-w106-recovery-public-receipt-v1","authority":"research_only","harness":HARNESS,"run_id":str(run_id),"payload_sha256":hashlib.sha256(plaintext).hexdigest(),"producer_source_commit":manifest["producer_source_commit"],"separator_source_commit":manifest["separator_source_commit"],"mnq_data_commit":MNQ_DATA_COMMIT,"mnq_source_subdir":"plaintext_csv","accepted_screen_parity_pass":True,"w106_metrics":replay.get("metrics"),"separator_events":sep.get("events"),"separator_aggregate":sep.get("aggregate"),"decision":sep.get("decision"),"promotion_authority":False,"runtime_authority":False,"broker_authority":False,"live_trading_change":False}

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--envelope",required=True); p.add_argument("--private-key",required=True); p.add_argument("--run-id",required=True); a=p.parse_args()
    print("MNQ_W106_RECOVERY_RECEIPT="+json.dumps(consume(Path(a.envelope),Path(a.private_key),a.run_id),sort_keys=True))
if __name__=="__main__": main()
