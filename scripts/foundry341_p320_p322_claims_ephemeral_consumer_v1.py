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

SCHEMA = "foundry341-p320-p322-claims-x25519-v1"
HARNESS = "foundry341_p320_p322_claim_acceptance_v1"
INFO = b"commandcenter-foundry341-p320-p322-claims-v1"
FOUNDRY_PR = 341
FOUNDRY_HEAD = "4e5bb6a9b210ef044f00e22f31b3989487dc0508"
CLAIMS = {
    "shared_evidence/claims/p320_fixed_global_combination_not_supported.v1.json": {
        "blob": "211ab50766d5033347c38893cb97a4bd5ef1e599",
        "evidence_id": "P320:fixed_global_combination_not_supported:2026-09-10",
        "status": "NOT_SUPPORTED",
        "run_id": 34464957322,
        "job_id": 102831249431,
        "head_sha": "c8af7ee761820ea210e1023a2ef8c54af8ec0961",
        "artifact_id": 10147113695,
        "artifact_sha256": "3718402fbd9ffb12cf431bdfb6909241becfb619148076e64a49457906b539e7",
    },
    "shared_evidence/claims/p321_calf_distinctness_supported.v1.json": {
        "blob": "e7fd51a39e2ab688ab6dfd1296aca80d8cd040bf",
        "evidence_id": "P321:calf_distinct_return_source_plausible:2026-09-10",
        "status": "SUPPORTED",
        "run_id": 34465008014,
        "job_id": 102831413622,
        "head_sha": "acb9e6a05733c6b565b418d3a9c5c2b4a6ad4b8a",
        "artifact_id": 10147128539,
        "artifact_sha256": "a3fc9bf95b2356cfceab61bfad3801ba96ffa55f3f508c1f0eb31398dde6afa6",
    },
    "shared_evidence/claims/p322_calf_us_combination_not_supported.v1.json": {
        "blob": "c34bcb87c9b6ce067e69ec73dcb819058fcb9797",
        "evidence_id": "P322:calf_us_combination_not_supported:2026-09-10",
        "status": "NOT_SUPPORTED",
        "run_id": 34465170560,
        "job_id": 102831928434,
        "head_sha": "075458982deda5958b441d6956c37e9852f637e4",
        "artifact_id": 10147194123,
        "artifact_sha256": "6a60a7ddaf58e0b421b7e2174ded7fa49e13e9628717c49cb22c49de3c01ba34",
    },
}


def b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps({"schema":SCHEMA,"run_id":str(run_id),"authority":"research_only","harness":HARNESS,"recipient_key_id":recipient_key_id}, sort_keys=True, separators=(",", ":")).encode()


def decrypt(envelope_path: Path, private_key_path: Path, run_id: str) -> bytes:
    env=json.loads(envelope_path.read_text(encoding="utf-8"))
    required={"schema","run_id","authority","harness","recipient_key_id","sender_public_b64","nonce_b64","ciphertext_b64","plaintext_sha256"}
    if set(env)!=required or env["schema"]!=SCHEMA or str(env["run_id"])!=str(run_id) or env["authority"]!="research_only" or env["harness"]!=HARNESS:
        raise RuntimeError("envelope contract mismatch")
    private=x25519.X25519PrivateKey.from_private_bytes(b64d(private_key_path.read_text(encoding="ascii").strip()))
    recipient_raw=private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id="sha256:"+hashlib.sha256(recipient_raw).hexdigest()
    if env["recipient_key_id"]!=key_id:
        raise RuntimeError("recipient key mismatch")
    sender_raw,nonce,ciphertext=b64d(env["sender_public_b64"]),b64d(env["nonce_b64"]),b64d(env["ciphertext_b64"])
    if len(sender_raw)!=32 or len(nonce)!=12:
        raise RuntimeError("invalid envelope key or nonce")
    aad_bytes=aad(run_id,key_id)
    shared=private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    key=HKDF(algorithm=hashes.SHA256(),length=32,salt=hashlib.sha256(aad_bytes).digest(),info=INFO).derive(shared)
    plaintext=ChaCha20Poly1305(key).decrypt(nonce,ciphertext,aad_bytes)
    if hashlib.sha256(plaintext).hexdigest()!=env["plaintext_sha256"]:
        raise RuntimeError("plaintext digest mismatch")
    return plaintext


def read_payload(plaintext: bytes) -> dict[str, dict]:
    expected_names={"manifest.json",*CLAIMS.keys()}
    with tarfile.open(fileobj=io.BytesIO(plaintext),mode="r:gz") as tf:
        names={m.name for m in tf.getmembers() if m.isfile()}
        if names!=expected_names:
            raise RuntimeError(f"payload file set mismatch: {sorted(names)}")
        for m in tf.getmembers():
            p=Path(m.name)
            if m.isdir(): continue
            if m.issym() or m.islnk() or p.is_absolute() or ".." in p.parts:
                raise RuntimeError("unsafe payload member")
        mf=tf.extractfile(tf.getmember("manifest.json"))
        if mf is None: raise RuntimeError("manifest missing")
        manifest=json.loads(mf.read().decode())
        expected_manifest={"schema":"foundry341-p320-p322-claims-payload-v1","harness":HARNESS,"authority":"research_only","foundry_pr":FOUNDRY_PR,"foundry_head_sha":FOUNDRY_HEAD,"claim_git_blobs":{p:v["blob"] for p,v in CLAIMS.items()}}
        if manifest!=expected_manifest:
            raise RuntimeError("manifest mismatch")
        out={}
        for path,spec in CLAIMS.items():
            f=tf.extractfile(tf.getmember(path))
            if f is None: raise RuntimeError(f"claim missing: {path}")
            raw=f.read()
            if git_blob_sha(raw)!=spec["blob"]:
                raise RuntimeError(f"Git blob mismatch: {path}")
            out[path]=json.loads(raw)
        return out


def validate(claims: dict[str,dict]) -> list[dict]:
    accepted=[]
    for path,spec in CLAIMS.items():
        claim=claims[path]
        if claim.get("schema")!="foundry.shared_evidence_claim.v1" or claim.get("evidence_id")!=spec["evidence_id"]:
            raise RuntimeError(f"claim identity mismatch: {path}")
        if (claim.get("claim") or {}).get("status")!=spec["status"]:
            raise RuntimeError(f"claim status mismatch: {path}")
        authority=claim.get("authority") or {}
        false_fields=["automatic_action_allowed","portfolio_ranking_authority","portfolio_allocation_authority","promotion_authority","runtime_mutation","broker_authority","live_trading_authority"]
        if authority.get("max_scope")!="RESEARCH_ONLY" or any(authority.get(k) is not False for k in false_fields):
            raise RuntimeError(f"authority exceeds release boundary: {path}")
        terminal=(claim.get("evidence") or {}).get("terminal_execution") or {}
        if terminal.get("execution_repository")!="XoticHaze/research-compute-public-" or terminal.get("run_id")!=spec["run_id"] or terminal.get("job_id")!=spec["job_id"] or terminal.get("head_sha")!=spec["head_sha"] or terminal.get("conclusion")!="success" or terminal.get("artifact_id")!=spec["artifact_id"] or terminal.get("artifact_sha256")!=spec["artifact_sha256"]:
            raise RuntimeError(f"terminal execution provenance mismatch: {path}")
        accepted.append({"evidence_id":spec["evidence_id"],"claim_git_blob_sha":spec["blob"],"source_run_id":spec["run_id"],"source_job_id":spec["job_id"],"status":spec["status"]})
    return accepted


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--envelope",required=True); p.add_argument("--private-key",required=True); p.add_argument("--run-id",required=True); args=p.parse_args()
    plaintext=decrypt(Path(args.envelope),Path(args.private_key),args.run_id)
    accepted=validate(read_payload(plaintext))
    receipt={"schema":"foundry341-p320-p322-claims-acceptance-receipt-v1","authority":"research_only","harness":HARNESS,"foundry_pr":FOUNDRY_PR,"foundry_head_sha":FOUNDRY_HEAD,"payload_sha256":hashlib.sha256(plaintext).hexdigest(),"accepted":accepted,"status":"PASS","protected_authority_crossed":False}
    print("FOUNDRY341_P320_P322_CLAIMS_RECEIPT="+json.dumps(receipt,sort_keys=True))

if __name__=="__main__": main()
