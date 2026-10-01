from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"m1_r19_encrypted_artifact_ingest_r20.py"
SPEC=importlib.util.spec_from_file_location("m1_ingest_r20",SCRIPT)
assert SPEC and SPEC.loader
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

def _sha(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()

def _fixture(tmp_path:Path):
    run_id="12345"
    key_id="sha256:"+"1"*64
    cipher=b"age-encrypted-bytes-only"
    envelope={
        "authority":"research_only",
        "ciphertext":{"path":mod.CIPHER_NAME,"sha256":_sha(cipher)},
        "encryption":{"algorithm":"age-x25519","recipient_key_id":key_id},
        "harness":mod.HARNESS,
        "job_id":"m1-r19-recovery-"+run_id,
        "mode":"sealed",
        "schema_version":"sealed-job-v1",
    }
    archive=tmp_path/"bridge.zip"
    with zipfile.ZipFile(archive,"w") as zf:
        zf.writestr(mod.CIPHER_NAME,cipher)
        zf.writestr(mod.ENVELOPE_NAME,json.dumps(envelope,sort_keys=True)+"\n")
    request={
        "schema":mod.REQUEST_SCHEMA,
        "r19_run_id":run_id,
        "recipient_key_id":key_id,
        "artifact_zip_sha256":mod.sha256_file(archive),
        "ciphertext_sha256":_sha(cipher),
        "encrypted_artifact_url":"https://example.invalid/encrypted-only.zip",
        "authority":"research_only",
        "protected_holdout_read":False,
        "live_trading_change":False,
    }
    request_path=tmp_path/"request.json"
    request_path.write_text(json.dumps(request),encoding="utf-8")
    return request_path,archive,cipher

def test_valid_encrypted_only_bridge_passes(tmp_path):
    request,archive,cipher=_fixture(tmp_path)
    out=tmp_path/"out"
    receipt=mod.validate_and_extract(request,archive,out)
    assert receipt["status"]=="PASS"
    assert receipt["encrypted_only"] is True
    assert receipt["plaintext_read"] is False
    assert (out/mod.CIPHER_NAME).read_bytes()==cipher
    assert sorted(p.name for p in out.iterdir())==[mod.CIPHER_NAME,mod.ENVELOPE_NAME]

def test_rejects_extra_file(tmp_path):
    request,archive,_=_fixture(tmp_path)
    with zipfile.ZipFile(archive,"a") as zf:
        zf.writestr("plaintext.txt","forbidden")
    node=json.loads(request.read_text())
    node["artifact_zip_sha256"]=mod.sha256_file(archive)
    request.write_text(json.dumps(node),encoding="utf-8")
    try:
        mod.validate_and_extract(request,archive,tmp_path/"out")
    except RuntimeError as exc:
        assert "file_set_rejected" in str(exc)
    else:
        raise AssertionError("extra file was accepted")

def test_rejects_recipient_drift(tmp_path):
    request,archive,_=_fixture(tmp_path)
    node=json.loads(request.read_text())
    node["recipient_key_id"]="sha256:"+"2"*64
    request.write_text(json.dumps(node),encoding="utf-8")
    try:
        mod.validate_and_extract(request,archive,tmp_path/"out")
    except RuntimeError as exc:
        assert "envelope_binding_mismatch" in str(exc)
    else:
        raise AssertionError("recipient drift was accepted")
