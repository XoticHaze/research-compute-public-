from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "foundry341-p318-claim-x25519-v1"
HARNESS = "foundry341_p318_claim_acceptance_v1"
INFO = b"commandcenter-foundry341-p318-claim-v1"
FOUNDRY_PR = 341
FOUNDRY_HEAD = "a570e8f60514bf4acb8d8ce2828c17bb3032dc20"
CLAIM_PATH = "shared_evidence/claims/p318_global_momentum_complementarity_supported.v1.json"
CLAIM_BLOB = "5ddd9f6743ebaefbdedf79fc7e3bd64f3fee66e6"
EXPECTED_RUN = 34464601482
EXPECTED_JOB = 102830106343
EXPECTED_SOURCE_HEAD = "43a9b898dfa84614f01bf587dd7da272bc592b82"
EXPECTED_ARTIFACT = 10146965181
EXPECTED_ARTIFACT_SHA = "9f67cf1a46d663f47042b83962ab20bfb492e38567d8f1cc5dfb1e36147eb90c"


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps({
        "schema": SCHEMA,
        "run_id": str(run_id),
        "authority": "research_only",
        "harness": HARNESS,
        "recipient_key_id": recipient_key_id,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def derive(shared: bytes, aad_bytes: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=hashlib.sha256(aad_bytes).digest(), info=INFO,
    ).derive(shared)


def decrypt(envelope_path: Path, private_key_path: Path, run_id: str) -> bytes:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    required = {"schema","run_id","authority","harness","recipient_key_id","sender_public_b64","nonce_b64","ciphertext_b64","plaintext_sha256"}
    if set(env) != required:
        raise RuntimeError("envelope field set mismatch")
    if env["schema"] != SCHEMA or str(env["run_id"]) != str(run_id):
        raise RuntimeError("run identity mismatch")
    if env["authority"] != "research_only" or env["harness"] != HARNESS:
        raise RuntimeError("authority/harness mismatch")
    private_raw = b64d(private_key_path.read_text(encoding="ascii").strip())
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    expected_key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env["recipient_key_id"] != expected_key_id:
        raise RuntimeError("recipient key mismatch")
    sender_raw, nonce, ciphertext = b64d(env["sender_public_b64"]), b64d(env["nonce_b64"]), b64d(env["ciphertext_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("invalid key or nonce length")
    aad_bytes = aad(str(run_id), expected_key_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(derive(shared, aad_bytes)).decrypt(nonce, ciphertext, aad_bytes)
    if hashlib.sha256(plaintext).hexdigest() != env["plaintext_sha256"]:
        raise RuntimeError("plaintext digest mismatch")
    return plaintext


def read_claim(plaintext: bytes) -> dict:
    with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:gz") as tf:
        names = {m.name for m in tf.getmembers() if m.isfile()}
        if names != {"manifest.json", CLAIM_PATH}:
            raise RuntimeError(f"payload file set mismatch: {sorted(names)}")
        for member in tf.getmembers():
            p = Path(member.name)
            if member.isdir():
                continue
            if member.issym() or member.islnk() or p.is_absolute() or ".." in p.parts:
                raise RuntimeError("unsafe payload member")
        mf = tf.extractfile(tf.getmember("manifest.json"))
        cf = tf.extractfile(tf.getmember(CLAIM_PATH))
        if mf is None or cf is None:
            raise RuntimeError("payload member missing")
        manifest = json.loads(mf.read().decode("utf-8"))
        claim_bytes = cf.read()
    expected_manifest = {
        "schema": "foundry341-p318-claim-payload-v1",
        "harness": HARNESS,
        "authority": "research_only",
        "foundry_pr": FOUNDRY_PR,
        "foundry_head_sha": FOUNDRY_HEAD,
        "claim_path": CLAIM_PATH,
        "claim_git_blob_sha": CLAIM_BLOB,
    }
    if manifest != expected_manifest:
        raise RuntimeError("payload manifest mismatch")
    if git_blob_sha(claim_bytes) != CLAIM_BLOB:
        raise RuntimeError("private claim Git blob mismatch")
    return json.loads(claim_bytes)


def validate(claim: dict) -> dict:
    if claim.get("schema") != "foundry.shared_evidence_claim.v1":
        raise RuntimeError("claim schema mismatch")
    if claim.get("evidence_id") != "P318:global_momentum_complementarity_supported:2026-09-10":
        raise RuntimeError("evidence identity mismatch")
    c = claim.get("claim") or {}
    if c.get("status") != "SUPPORTED" or c.get("claim_type") != "diagnostic.p318_global_momentum_complementarity":
        raise RuntimeError("claim state mismatch")
    authority = claim.get("authority") or {}
    required_false = ["automatic_action_allowed","portfolio_ranking_authority","portfolio_allocation_authority","promotion_authority","runtime_mutation","broker_authority","live_trading_authority"]
    if authority.get("max_scope") != "RESEARCH_ONLY" or any(authority.get(k) is not False for k in required_false):
        raise RuntimeError("claim authority exceeds release boundary")
    terminal = (claim.get("evidence") or {}).get("terminal_execution") or {}
    expected = {
        "execution_repository": "XoticHaze/research-compute-public-",
        "workflow": ".github/workflows/p318-global-momentum-redundancy-r1.yml",
        "public_pr": 804,
        "run_id": EXPECTED_RUN,
        "job_id": EXPECTED_JOB,
        "job_started_at": "2026-09-10T10:09:56.8962051Z",
        "head_sha": EXPECTED_SOURCE_HEAD,
        "conclusion": "success",
        "artifact_id": EXPECTED_ARTIFACT,
        "artifact_sha256": EXPECTED_ARTIFACT_SHA,
    }
    if terminal != expected:
        raise RuntimeError("terminal execution provenance mismatch")
    decision = claim.get("decision") or {}
    if decision.get("disposition") != "GLOBAL_MOMENTUM_COMPLEMENTARITY_SUPPORTED_FOR_ONE_FROZEN_UTILITY_TEST":
        raise RuntimeError("decision disposition mismatch")
    blocked = set(decision.get("blocked_questions") or [])
    if blocked != {"Geography ETF product mining", "Correlation-threshold rescue", "Weight optimization"}:
        raise RuntimeError("blocked-question freeze mismatch")
    return {
        "evidence_id": claim["evidence_id"],
        "source_run_id": EXPECTED_RUN,
        "source_job_id": EXPECTED_JOB,
        "claim_git_blob_sha": CLAIM_BLOB,
        "foundry_head_sha": FOUNDRY_HEAD,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    plaintext = decrypt(Path(args.envelope), Path(args.private_key), args.run_id)
    accepted = validate(read_claim(plaintext))
    receipt = {
        "schema": "foundry341-p318-claim-acceptance-receipt-v1",
        "authority": "research_only",
        "harness": HARNESS,
        "foundry_pr": FOUNDRY_PR,
        "foundry_head_sha": FOUNDRY_HEAD,
        "payload_sha256": hashlib.sha256(plaintext).hexdigest(),
        "accepted": accepted,
        "status": "PASS",
        "protected_authority_crossed": False,
    }
    print("FOUNDRY341_P318_CLAIM_RECEIPT=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
