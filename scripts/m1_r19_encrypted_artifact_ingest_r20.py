from __future__ import annotations

"""Validate and unpack only an encrypted M1 R19 bridge artifact.

Input is a ZIP containing exactly:
- m1-payload.tar.gz.age
- sealed-job.json

This tool never decrypts or interprets private scientific payload bytes. It
binds the encrypted artifact to one exact R19 run/recipient and copies the two
validated files to a caller-owned output directory.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

SCHEMA="research_compute.m1_r19_encrypted_artifact_ingest.r20.v1"
REQUEST_SCHEMA="research_compute.m1_r19_encrypted_artifact_ingest_fire.r20.v1"
CIPHER_NAME="m1-payload.tar.gz.age"
ENVELOPE_NAME="sealed-job.json"
HARNESS="research_foundry_m1_h12_r18_v1"

def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def load_request(path:Path)->dict:
    node=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(node,dict) or node.get("schema")!=REQUEST_SCHEMA:
        raise RuntimeError("ingest_request_schema_rejected")
    run_id=str(node.get("r19_run_id") or "").strip()
    if not run_id.isdigit():
        raise RuntimeError("ingest_request_run_id_rejected")
    if node.get("authority")!="research_only":
        raise RuntimeError("ingest_request_authority_rejected")
    if node.get("protected_holdout_read") is not False or node.get("live_trading_change") is not False:
        raise RuntimeError("ingest_request_safety_boundary_rejected")
    for key in ("artifact_zip_sha256","ciphertext_sha256"):
        value=str(node.get(key) or "").lower()
        if len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
            raise RuntimeError("ingest_request_digest_rejected:"+key)
    key_id=str(node.get("recipient_key_id") or "")
    if not key_id.startswith("sha256:") or len(key_id)!=71:
        raise RuntimeError("ingest_request_recipient_key_rejected")
    url=str(node.get("encrypted_artifact_url") or "")
    if not url.startswith("https://"):
        raise RuntimeError("ingest_request_url_rejected")
    return node

def validate_and_extract(request_path:Path,archive_path:Path,output_dir:Path)->dict:
    req=load_request(request_path)
    observed_zip_sha=sha256_file(archive_path)
    if observed_zip_sha!=req["artifact_zip_sha256"]:
        raise RuntimeError("encrypted_artifact_zip_digest_mismatch")

    output_dir.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive_path,"r") as zf:
        names=sorted(zf.namelist())
        if names!=[CIPHER_NAME,ENVELOPE_NAME]:
            raise RuntimeError("encrypted_artifact_file_set_rejected")
        for info in zf.infolist():
            p=Path(info.filename)
            if p.is_absolute() or ".." in p.parts or info.is_dir():
                raise RuntimeError("encrypted_artifact_member_rejected")
            target=(output_dir/p.name).resolve()
            if output_dir.resolve() not in target.parents:
                raise RuntimeError("encrypted_artifact_escape_rejected")
            with zf.open(info,"r") as src,target.open("wb") as dst:
                shutil.copyfileobj(src,dst)

    cipher=output_dir/CIPHER_NAME
    envelope=output_dir/ENVELOPE_NAME
    observed_cipher_sha=sha256_file(cipher)
    if observed_cipher_sha!=req["ciphertext_sha256"]:
        raise RuntimeError("ciphertext_digest_mismatch")

    node=json.loads(envelope.read_text(encoding="utf-8"))
    expected_envelope={
        "authority":"research_only",
        "ciphertext":{"path":CIPHER_NAME,"sha256":observed_cipher_sha},
        "encryption":{
            "algorithm":"age-x25519",
            "recipient_key_id":req["recipient_key_id"],
        },
        "harness":HARNESS,
        "job_id":"m1-r19-recovery-"+str(req["r19_run_id"]),
        "mode":"sealed",
        "schema_version":"sealed-job-v1",
    }
    if node!=expected_envelope:
        raise RuntimeError("sealed_envelope_binding_mismatch")

    return {
        "schema":SCHEMA,
        "status":"PASS",
        "r19_run_id":str(req["r19_run_id"]),
        "artifact_zip_sha256":observed_zip_sha,
        "ciphertext_sha256":observed_cipher_sha,
        "recipient_key_id":req["recipient_key_id"],
        "file_set":[CIPHER_NAME,ENVELOPE_NAME],
        "encrypted_only":True,
        "plaintext_read":False,
        "protected_holdout_read":False,
        "live_trading_change":False,
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--request",required=True)
    ap.add_argument("--archive",required=True)
    ap.add_argument("--output-dir",required=True)
    args=ap.parse_args()
    receipt=validate_and_extract(Path(args.request),Path(args.archive),Path(args.output_dir))
    print(json.dumps(receipt,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
