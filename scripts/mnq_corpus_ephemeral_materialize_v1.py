from __future__ import annotations
"""Materialize the already-admitted fixed MNQ replay member into canonical session input_root.

Transport/data-plane only. Reuses the proven fixed artifact ticket consumer and
does not own strategy, runtime, broker, promotion, or live authority.
"""
import argparse, json, os, zipfile
from pathlib import Path
import mnq_corpus_ephemeral_consumer_v1 as corpus
from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

MEMBER="output/mnq-strategy-backtest-12min.csv"
OUTPUT_NAME="mnq-strategy-backtest-12min.csv"

def materialize_ticket(ticket_bytes:bytes, output_root:Path)->dict:
    payload=corpus._fetch_artifact(ticket_bytes)
    receipt=corpus._validate_zip(payload)
    with zipfile.ZipFile(__import__("io").BytesIO(payload)) as zf:
        raw=zf.read(MEMBER)
    if corpus.sha256_bytes(raw)!=corpus.DATASET_SHA256:
        raise RuntimeError("MNQ materialized member digest mismatch")
    output_root=output_root.resolve(); output_root.mkdir(parents=True,exist_ok=True)
    target=(output_root/OUTPUT_NAME).resolve()
    if output_root not in target.parents: raise RuntimeError("MNQ output path rejected")
    target.write_bytes(raw)
    try: os.chmod(target,0o600)
    except OSError: pass
    return {"schema":"mnq-corpus-input-root-materialization-v1","relative_path":OUTPUT_NAME,"sha256":corpus.DATASET_SHA256,"bytes":len(raw),"research_only":True,"strategy_spec_write":False,"runtime_activation":False,"broker_submit":False,"live_trading_change":False}

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--envelope",type=Path,required=True);p.add_argument("--ciphertext",type=Path,required=True);p.add_argument("--private-key",type=Path,required=True);p.add_argument("--run-id",required=True);p.add_argument("--response-root",required=True);p.add_argument("--output-root",type=Path,required=True);a=p.parse_args()
    envelope=json.loads(a.envelope.read_text());ciphertext=a.ciphertext.read_bytes()
    ticket=decrypt_assembled_ciphertext(envelope=envelope,ciphertext=ciphertext,private_key_path=a.private_key,expected_schema=corpus.SCHEMA,expected_run_id=a.run_id,expected_harness=corpus.HARNESS,response_root=a.response_root)
    out=materialize_ticket(ticket,a.output_root)
    print("MNQ_CORPUS_INPUT_ROOT_MATERIALIZED="+json.dumps(out,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
