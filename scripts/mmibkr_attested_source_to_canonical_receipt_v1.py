from __future__ import annotations
"""Fail-closed receipt adapter for the generalized canonical research dispatcher."""
import argparse, json, re
from pathlib import Path

IN_SCHEMA="mmibkr.attested_source_materialization.v2"
OUT_SCHEMA="mmibkr.private_source_materialization.v1"
REPOSITORY="XoticHaze/mm-IBKR"
SHA1=re.compile(r"^[0-9a-f]{40}$")
SHA256=re.compile(r"^[0-9a-f]{64}$")

def adapt(node:dict)->dict:
    if not isinstance(node,dict) or node.get("schema")!=IN_SCHEMA or node.get("ok") is not True:
        raise ValueError("attested source materialization rejected")
    sha=str(node.get("source_sha") or "").lower()
    archive=str(node.get("source_archive_sha256") or "").lower()
    root=Path(str(node.get("source_root") or "")).resolve()
    if not SHA1.fullmatch(sha) or not SHA256.fullmatch(archive) or not root.is_dir():
        raise ValueError("attested source identity rejected")
    required_false=("private_repository_token_used","broker_credentials_used","plaintext_emitted","live_execution_allowed")
    if any(node.get(k) is not False for k in required_false):
        raise ValueError("attested source authority boundary rejected")
    if node.get("vault_attestation_verified") is not True:
        raise ValueError("source vault attestation rejected")
    return {
        "schema":OUT_SCHEMA,
        "mmibkr_repository":REPOSITORY,
        "mmibkr_head":sha,
        "source_archive_sha256":archive,
        "source_root":str(root),
        "broker_credentials_materialized":False,
        "tws_credentials_required":False,
        "source_token_emitted":False,
        "paper_or_live_authority":False,
    }

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    out=adapt(json.loads(Path(a.input).read_text(encoding="utf-8")))
    Path(a.output).write_text(json.dumps(out,sort_keys=True)+"\n",encoding="utf-8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
