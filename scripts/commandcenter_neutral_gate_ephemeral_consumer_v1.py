from __future__ import annotations
"""Fixed, run-bound neutral broker policy regression through the EXISTING X25519 capsule.

No private Cloudflare credentials, no API calls, no arbitrary command interface.
The five canonical CommandCenter inputs are admitted only at exact Git blob SHAs.
"""
import argparse, base64, hashlib, io, json, os, subprocess, sys, tarfile, tempfile
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from commandcenter_ledger_ephemeral_consumer_v1 import _derive, _b64d, sha256_bytes
from opaque_bidirectional_capsule_p256_aesgcm_v1 import (
    SCHEMA as CANONICAL_SCHEMA,
    FIELDS as CANONICAL_FIELDS,
    open_capsule as open_canonical_capsule,
)

SCHEMA = "commandcenter-neutral-credential-gates-x25519-v1"
HARNESS = "commandcenter_neutral_broker_credential_gates_v1"
AUTHORITY = "offline_source_contract_tests_only"
INFO = b"commandcenter-neutral-credential-gates-v1"
MANIFEST_SCHEMA = "commandcenter-neutral-credential-gates-payload-v1"
EXPECTED_GIT_BLOBS = {
    "scripts/security/validate_neutral_broker_editor_token_policy.py": "0df525a4ef7349b95b563554ac60aab36a8a42ce",
    "tests/test_neutral_broker_editor_token_policy.py": "949322273c704e830a14ed2ca70da6ef5cd0fe92",
    "tests/test_shared_compute_neutral_gate_20261012.py": "eeb48cde549234a5062d93953d5872db5b9e08a7",
    "config/security/shared_compute_neutral_broker_editor_bootstrap_gate_v1.json": "7d55e21b40353615c2eac82caba2c96e478c2dee",
    "config/security/cloudflare_deploy_credential_migration_v1.json": "364ea27a34c7af5d430cefb0ec431b11f552765a",
}
POLICY_ONLY_FILES = {
    "scripts/security/validate_neutral_broker_editor_token_policy.py",
    "tests/test_neutral_broker_editor_token_policy.py",
}
MAX_ARCHIVE = 200_000

def _git_blob(contents: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(contents)).encode() + b"\0" + contents).hexdigest()

def _aad(run_id: str, key_id: str) -> bytes:
    return json.dumps({"schema": SCHEMA, "run_id": str(run_id), "authority": AUTHORITY,
                       "harness": HARNESS, "recipient_key_id": key_id},
                       separators=(",", ":"), sort_keys=True).encode()

def _open_legacy_capsule(env: dict, private_key: Path, run_id: str) -> bytes:
    required = {"schema","run_id","authority","harness","recipient_key_id",
                "sender_public_b64","nonce_b64","ciphertext_b64","plaintext_sha256"}
    if set(env) != required or env["schema"] != SCHEMA or str(env["run_id"]) != str(run_id):
        raise ValueError("neutral envelope identity mismatch")
    if env["authority"] != AUTHORITY or env["harness"] != HARNESS:
        raise ValueError("neutral envelope purpose mismatch")
    raw = _b64d(private_key.read_text().strip())
    if len(raw) != 32: raise ValueError("one-run recipient key rejected")
    private = x25519.X25519PrivateKey.from_private_bytes(raw)
    pub = private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    key_id = "sha256:" + hashlib.sha256(pub).hexdigest()
    if env["recipient_key_id"] != key_id: raise ValueError("recipient fingerprint rejected")
    sender = _b64d(env["sender_public_b64"])
    nonce = _b64d(env["nonce_b64"])
    if len(sender) != 32 or len(nonce) != 12: raise ValueError("sender key or nonce malformed")
    ciphertext = _b64d(env["ciphertext_b64"])
    if len(ciphertext) > 300_000: raise ValueError("oversized ciphertext")
    aad = _aad(str(run_id),key_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender))
    content = ChaCha20Poly1305(_derive(shared,aad,info=INFO)).decrypt(nonce,ciphertext,aad)
    if len(content) > MAX_ARCHIVE or sha256_bytes(content) != env["plaintext_sha256"]:
        raise ValueError("decrypted capsule size/digest rejected")
    return content


def consume(envelope: Path, private_key: Path, run_id: str,
            canonical_private_key: Path | None = None) -> dict:
    env = json.loads(envelope.read_text())
    if env.get("schema") == CANONICAL_SCHEMA:
        # Reuse the already-governed P-256 / HKDF-SHA256 / AES-256-GCM
        # profile. No public plaintext digest, purpose or source metadata.
        if canonical_private_key is None or set(env) != CANONICAL_FIELDS:
            raise ValueError("canonical capsule recipient or shape rejected")
        content = open_canonical_capsule(
            env, recipient_private_b64=canonical_private_key.read_text().strip(),
            expected_run_id=str(run_id), expected_direction="request",
        )
        if len(content) > MAX_ARCHIVE:
            raise ValueError("canonical capsule size rejected")
        capsule_profile = "canonical_p256_aesgcm_v1"
    else:
        # Explicit, bounded compatibility for the previously proven
        # X25519 rendezvous. Do NOT treat this as canonical-profile privacy.
        content = _open_legacy_capsule(env, private_key, run_id)
        capsule_profile = "legacy_x25519_v1"
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        with tarfile.open(fileobj=io.BytesIO(content),mode="r:gz") as archive:
            members=archive.getmembers()
            names={m.name for m in members}
            allowed=(set(EXPECTED_GIT_BLOBS)|{"payload-manifest.json"},
                     POLICY_ONLY_FILES|{"payload-manifest.json"})
            if len(members)!=len(names) or names not in allowed:
                raise ValueError("archive allowlist mismatch")
            for member in members:
                if not member.isfile() or member.size<1 or member.size>80_000:
                    raise ValueError("archive member type/size rejected")
                data=archive.extractfile(member).read()
                target=root/member.name
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(data)
        manifest=json.loads((root/"payload-manifest.json").read_text())
        if set(manifest)!={"schema","harness","files"} or manifest["schema"]!=MANIFEST_SCHEMA or manifest["harness"]!=HARNESS:
            raise ValueError("payload purpose/manifest rejected")
        selected=set(manifest["files"])
        if selected not in (set(EXPECTED_GIT_BLOBS),POLICY_ONLY_FILES):
            raise ValueError("payload digest member set rejected")
        if selected != names - {"payload-manifest.json"}:
            raise ValueError("manifest/archive member identity rejected")
        for rel in sorted(selected):
            expected_blob=EXPECTED_GIT_BLOBS[rel]
            contents=(root/rel).read_bytes()
            if _git_blob(contents)!=expected_blob:
                raise ValueError("immutable canonical source Git blob mismatch")
            if sha256_bytes(contents)!=manifest["files"][rel]:
                raise ValueError("payload inner sha256 mismatch")
        checks={}
        test_patterns=(
            (("neutral_stage_truth", "test_shared_compute_neutral_gate_20261012.py"),
             ("single_worker_editor_policy", "test_neutral_broker_editor_token_policy.py"))
            if selected == set(EXPECTED_GIT_BLOBS)
            else (("single_worker_editor_policy", "test_neutral_broker_editor_token_policy.py"),)
        )
        for label,pattern in test_patterns:
            command=[sys.executable,"-m","unittest","discover","-s","tests","-p",pattern,"-v"]
            completed=subprocess.run(command,cwd=root,stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90,
                env={"PATH":os.environ.get("PATH","/usr/bin:/bin"),
                     "PYTHONDONTWRITEBYTECODE":"1","PYTHONNOUSERSITE":"1"})
            checks[label]=(completed.returncode==0)
        return {
            "schema":"commandcenter-neutral-broker-credential-gates-receipt-v1",
            "trust_mode":"public_encrypted",
            "authority":AUTHORITY,
            "run_id":str(run_id),
            "status":"PASS" if all(checks.values()) else "FAIL",
            "checks":checks,
            "pinned_source_member_count":len(selected),
            "encrypted_input":True,
            "capsule_profile":capsule_profile,
            "private_plaintext_emitted":False,
            "cloudflare_mutations":False,
            "broker_token_created":False,
            "live_authority_changed":False,
        }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--envelope",required=True)
    p.add_argument("--private-key",required=True)
    p.add_argument("--run-id",required=True)
    p.add_argument("--canonical-private-key")
    args=p.parse_args()
    try:
        result=consume(Path(args.envelope),Path(args.private_key),args.run_id,
            Path(args.canonical_private_key) if args.canonical_private_key else None)
    except Exception:
        result={"schema":"commandcenter-neutral-broker-credential-gates-receipt-v1",
                "trust_mode":"public_encrypted","run_id":str(args.run_id),
                "status":"FAIL_CLOSED","private_plaintext_emitted":False,
                "cloudflare_mutations":False,"broker_token_created":False}
    print("NEUTRAL_BROKER_GATE_RECEIPT="+json.dumps(result,sort_keys=True))
    raise SystemExit(0 if result["status"]=="PASS" else 1)

if __name__=="__main__":
    main()
