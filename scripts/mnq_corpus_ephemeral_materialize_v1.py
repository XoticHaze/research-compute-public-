from __future__ import annotations
"""Materialize the already-admitted fixed MNQ replay member into canonical session input_root.

Transport/data-plane only. Accepts either the proven encrypted short-lived
artifact ticket or the exact admitted corpus bytes directly. Scientific
identity is the immutable inner corpus SHA/byte contract; disposable artifact
retention is not data authority.
"""
import argparse, gzip, io, json, os, zipfile
from pathlib import Path

import mnq_corpus_ephemeral_consumer_v1 as corpus
from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

MEMBER="output/mnq-strategy-backtest-12min.csv"
OUTPUT_NAME="mnq-strategy-backtest-12min.csv"
DATASET_BYTES=18_026_715


def _write_member(raw:bytes, output_root:Path, *, transport_mode:str)->dict:
    if corpus.sha256_bytes(raw)!=corpus.DATASET_SHA256:
        raise RuntimeError("MNQ materialized member digest mismatch")
    output_root=output_root.resolve(); output_root.mkdir(parents=True,exist_ok=True)
    target=(output_root/OUTPUT_NAME).resolve()
    if output_root not in target.parents: raise RuntimeError("MNQ output path rejected")
    target.write_bytes(raw)
    try: os.chmod(target,0o600)
    except OSError: pass
    return {
        "schema":"mnq-corpus-input-root-materialization-v1",
        "relative_path":OUTPUT_NAME,
        "sha256":corpus.DATASET_SHA256,
        "bytes":len(raw),
        "transport_mode":transport_mode,
        "research_only":True,
        "strategy_spec_write":False,
        "runtime_activation":False,
        "broker_submit":False,
        "live_trading_change":False,
    }


def materialize_ticket(ticket_bytes:bytes, output_root:Path)->dict:
    payload=corpus._fetch_artifact(ticket_bytes)
    corpus._validate_zip(payload)
    with zipfile.ZipFile(__import__("io").BytesIO(payload)) as zf:
        raw=zf.read(MEMBER)
    return _write_member(raw,output_root,transport_mode="artifact_ticket")


def materialize_payload(payload_bytes:bytes, output_root:Path)->dict:
    """Prefer exact direct corpus bytes; retain the old ticket route for compatibility."""
    digest=corpus.sha256_bytes(payload_bytes)
    if len(payload_bytes)==DATASET_BYTES:
        if digest!=corpus.DATASET_SHA256:
            raise RuntimeError("MNQ direct corpus identity mismatch")
        return _write_member(payload_bytes,output_root,transport_mode="direct_exact_corpus")

    # Existing non-Actions corpus producers gzip before X25519 encryption to keep
    # the public exchange bounded. Accept that transport encoding only after
    # bounded decompression and the same exact inner corpus identity check.
    if payload_bytes.startswith(b"\\x1f\\x8b"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(payload_bytes),mode="rb") as handle:
                raw=handle.read(DATASET_BYTES+1)
                if handle.read(1):
                    raise RuntimeError("MNQ gzip corpus expands beyond fixed byte cap")
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("MNQ gzip corpus payload invalid") from exc
        if len(raw)!=DATASET_BYTES or corpus.sha256_bytes(raw)!=corpus.DATASET_SHA256:
            raise RuntimeError("MNQ gzip corpus identity mismatch")
        return _write_member(raw,output_root,transport_mode="direct_exact_corpus_gzip")

    # A direct corpus with the wrong byte count must not be silently interpreted
    # as another data format. Only the established ticket schema is an alternate.
    try:
        node=json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("MNQ encrypted payload is neither exact corpus nor artifact ticket") from exc
    if not isinstance(node,dict) or node.get("schema")!=corpus.TICKET_SCHEMA:
        raise RuntimeError("MNQ encrypted payload schema rejected")
    return materialize_ticket(payload_bytes,output_root)


def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--envelope",type=Path,required=True);p.add_argument("--ciphertext",type=Path,required=True);p.add_argument("--private-key",type=Path,required=True);p.add_argument("--run-id",required=True);p.add_argument("--response-root",required=True);p.add_argument("--output-root",type=Path,required=True);a=p.parse_args()
    envelope=json.loads(a.envelope.read_text());ciphertext=a.ciphertext.read_bytes()
    payload=decrypt_assembled_ciphertext(envelope=envelope,ciphertext=ciphertext,private_key_path=a.private_key,expected_schema=corpus.SCHEMA,expected_run_id=a.run_id,expected_harness=corpus.HARNESS,response_root=a.response_root)
    out=materialize_payload(payload,a.output_root)
    print("MNQ_CORPUS_INPUT_ROOT_MATERIALIZED="+json.dumps(out,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
