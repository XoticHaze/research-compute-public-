from __future__ import annotations

"""Run-bound encrypted acceptance for the Foundry #341 forward contract.

Only four exact private JSON blobs cross the public/private seam, sealed to a one-run
X25519 recipient. The consumer verifies their Git blob identities and fail-closed release
semantics, then emits a sanitized receipt. No private plaintext is committed publicly.
"""

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

SCHEMA = "foundry341-forward-pytest-x25519-v1"
HARNESS = "foundry341_forward_observer_pytest_v1"
INFO = b"commandcenter-foundry341-forward-pytest-v1"
FOUNDRY_PR = 341
FOUNDRY_HEAD = "53931308f798c107ab0aed16da0a1268ec589266"
CONTRACT = "research/forward_observation_contract_spmo_smallvalue_20260910.json"
NEXT = "research/forward_observation_next_executable_spmo_smallvalue_20260910.json"
UTILITY = "shared_evidence/claims/p303_p304_spmo_smallvalue_fixed_utility_supported.v1.json"
COST = "shared_evidence/claims/p305_spmo_smallvalue_cost_robustness_supported.v1.json"
EXPECTED_GIT_BLOBS = {
    CONTRACT: "8c8dbf8a388fa58caa58584d239d52cc73985ae2",
    NEXT: "89912ee83c4ea817d59c71915eb368be2fe59380",
    UTILITY: "c46d42d735dd4b131cc0fc21ea1a53e9df1dffe6",
    COST: "ff287f13b6ca0d500d9e1820b65beac866f50b7b",
}
PAYLOAD_FILES = set(EXPECTED_GIT_BLOBS)
ALLOWED_FILES = {"manifest.json", *PAYLOAD_FILES}
FALSE_AUTHORITY = (
    "portfolio_ranking_authority",
    "portfolio_allocation_authority",
    "runtime_mutation",
    "broker_authority",
    "live_trading_authority",
)


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _git_blob_sha(data: bytes) -> str:
    prefix = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(prefix + data).hexdigest()


def _aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {"schema": SCHEMA, "run_id": str(run_id), "authority": "research_only", "harness": HARNESS, "recipient_key_id": recipient_key_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive(shared: bytes, aad: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(aad).digest(), info=INFO).derive(shared)


def _decrypt(envelope_path: Path, private_key_path: Path, expected_run_id: str) -> bytes:
    env = json.loads(envelope_path.read_text(encoding="utf-8"))
    required = {"schema", "run_id", "authority", "harness", "recipient_key_id", "sender_public_b64", "nonce_b64", "ciphertext_b64", "plaintext_sha256"}
    if set(env) != required:
        raise RuntimeError("ephemeral envelope field set mismatch")
    if env["schema"] != SCHEMA or str(env["run_id"]) != str(expected_run_id):
        raise RuntimeError("ephemeral envelope run identity mismatch")
    if env["authority"] != "research_only" or env["harness"] != HARNESS:
        raise RuntimeError("ephemeral envelope authority/harness mismatch")
    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    expected_key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if env["recipient_key_id"] != expected_key_id:
        raise RuntimeError("recipient key fingerprint mismatch")
    sender_raw, nonce, ciphertext = _b64d(env["sender_public_b64"]), _b64d(env["nonce_b64"]), _b64d(env["ciphertext_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("ephemeral envelope key/nonce length invalid")
    aad = _aad(str(expected_run_id), expected_key_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(_derive(shared, aad)).decrypt(nonce, ciphertext, aad)
    if hashlib.sha256(plaintext).hexdigest() != env["plaintext_sha256"]:
        raise RuntimeError("decrypted payload digest mismatch")
    return plaintext


def _read_payload(plaintext: bytes) -> tuple[dict, dict[str, bytes]]:
    with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:gz") as tf:
        members = [m for m in tf.getmembers() if m.isfile()]
        names = {m.name for m in members}
        if names != ALLOWED_FILES:
            raise RuntimeError(f"payload file set mismatch: {sorted(names)}")
        for member in tf.getmembers():
            p = Path(member.name)
            if member.isdir():
                continue
            if member.issym() or member.islnk() or p.is_absolute() or ".." in p.parts:
                raise RuntimeError("unsafe payload member")
        blobs = {}
        for name in ALLOWED_FILES:
            f = tf.extractfile(tf.getmember(name))
            if f is None:
                raise RuntimeError(f"missing payload member: {name}")
            blobs[name] = f.read()
    manifest = json.loads(blobs.pop("manifest.json").decode("utf-8"))
    required = {"schema", "harness", "authority", "foundry_pr", "foundry_head_sha", "git_blob_sha"}
    if set(manifest) != required:
        raise RuntimeError("manifest field set mismatch")
    if manifest["schema"] != "foundry341-forward-contract-payload-v1" or manifest["harness"] != HARNESS or manifest["authority"] != "research_only":
        raise RuntimeError("payload schema/harness/authority mismatch")
    if int(manifest["foundry_pr"]) != FOUNDRY_PR or manifest["foundry_head_sha"] != FOUNDRY_HEAD:
        raise RuntimeError("payload target mismatch")
    if manifest["git_blob_sha"] != EXPECTED_GIT_BLOBS:
        raise RuntimeError("manifest Git blob map mismatch")
    for rel, expected in EXPECTED_GIT_BLOBS.items():
        if _git_blob_sha(blobs[rel]) != expected:
            raise RuntimeError(f"private Git blob identity mismatch: {rel}")
    return manifest, blobs


def _validate_semantics(blobs: dict[str, bytes]) -> dict:
    contract = json.loads(blobs[CONTRACT])
    nxt = json.loads(blobs[NEXT])
    utility = json.loads(blobs[UTILITY])
    cost = json.loads(blobs[COST])
    if contract.get("schema") != "foundry.research.forward_observation_contract.v1":
        raise RuntimeError("forward contract schema mismatch")
    candidate = contract.get("candidate") or {}
    eligibility = contract.get("eligibility") or {}
    boundaries = contract.get("boundaries") or {}
    if candidate.get("weights") != {"SPMO": 0.5, "IJS": 0.5} or candidate.get("matched_control") != {"SPY": 0.5, "IJR": 0.5}:
        raise RuntimeError("frozen candidate/control identity mismatch")
    if candidate.get("cost_bps_endpoints") != [25, 50] or candidate.get("cadence") != "monthly":
        raise RuntimeError("frozen cost/cadence mismatch")
    if candidate.get("evidence_claim_path") != UTILITY or candidate.get("cost_robustness_claim_path") != COST:
        raise RuntimeError("supporting claim path mismatch")
    if eligibility.get("required_claim_status") != "SUPPORTED" or eligibility.get("automatic_action_allowed") is not False:
        raise RuntimeError("eligibility fail-closed contract mismatch")
    if eligibility.get("first_eligible_decision_boundary") != "2026-09-30" or eligibility.get("first_maturity_boundary") != "2026-10-30":
        raise RuntimeError("forward boundary mismatch")
    for key in (*FALSE_AUTHORITY, "promotion_authority"):
        if boundaries.get(key) is not False:
            raise RuntimeError(f"forward contract exceeds authority: {key}")
    if nxt.get("schema") != "foundry.research.forward_observation_next_executable.v1":
        raise RuntimeError("next executable schema mismatch")
    if nxt.get("decision_boundary", {}).get("date") != "2026-09-30" or nxt.get("maturity_boundary", {}).get("not_before") != "2026-10-30":
        raise RuntimeError("next executable boundary mismatch")
    if nxt.get("scientific_freeze", {}).get("candidate_weights") != {"SPMO": 0.5, "IJS": 0.5}:
        raise RuntimeError("next executable candidate freeze mismatch")
    if nxt.get("scientific_freeze", {}).get("matched_control_weights") != {"SPY": 0.5, "IJR": 0.5}:
        raise RuntimeError("next executable control freeze mismatch")
    for claim, label in ((utility, "utility"), (cost, "cost")):
        if claim.get("schema") != "foundry.shared_evidence_claim.v1" or (claim.get("claim") or {}).get("status") != "SUPPORTED":
            raise RuntimeError(f"{label} support claim changed")
        authority = claim.get("authority") or {}
        if authority.get("max_scope") != "RESEARCH_ONLY" or authority.get("automatic_action_allowed") is not False:
            raise RuntimeError(f"{label} support claim exceeds authority")
    return {
        "contract_id": contract["contract_id"],
        "utility_evidence_id": utility["evidence_id"],
        "cost_evidence_id": cost["evidence_id"],
        "decision_boundary": eligibility["first_eligible_decision_boundary"],
        "maturity_boundary": eligibility["first_maturity_boundary"],
    }


def consume(envelope_path: Path, private_key_path: Path, expected_run_id: str) -> dict:
    plaintext = _decrypt(envelope_path, private_key_path, expected_run_id)
    _, blobs = _read_payload(plaintext)
    semantic = _validate_semantics(blobs)
    return {
        "schema": "foundry341-forward-contract-acceptance-receipt-v1",
        "authority": "research_only",
        "harness": HARNESS,
        "foundry_pr": FOUNDRY_PR,
        "foundry_head_sha": FOUNDRY_HEAD,
        "payload_sha256": hashlib.sha256(plaintext).hexdigest(),
        "git_blob_identity_verified": True,
        "semantic_acceptance": semantic,
        "status": "PASS",
        "protected_authority_crossed": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True)
    p.add_argument("--private-key", required=True)
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    receipt = consume(Path(args.envelope), Path(args.private_key), args.run_id)
    print("FOUNDRY341_FORWARD_CONTRACT_RECEIPT=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
