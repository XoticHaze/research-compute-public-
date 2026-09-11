from __future__ import annotations

import argparse,base64,hashlib,json,subprocess,sys,tarfile,tempfile
from pathlib import Path
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA="mm-survivor-forward-x25519-v1"
HARNESS="mm_completed_trade_evidence_ui_acceptance_v1"
INFO=b"commandcenter-mm-survivor-forward-v1"
EXPECTED_MM_COMMIT="964c0e37841a8c3b0c520b286d62478ce3a787b8"
FILES={
    "ui-react/src/components/CapitalReadinessPanel.jsx":"dea01fcf557402ef17dcbfe5d6a77c673b3a48a8",
    "tests/test_capital_readiness_panel_completed_trade_evidence_contract.py":"cdbfd1de59330c751a7d66d053bf872b7277c6aa",
}

def h(b): return hashlib.sha256(b).hexdigest()
def b64(v): return base64.b64decode(v.encode("ascii"),validate=True)
def blob(raw): return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()
def aad(run,key): return json.dumps({"schema":SCHEMA,"run_id":str(run),"harness":HARNESS,"mm_commit":EXPECTED_MM_COMMIT,"recipient_key_id":key},sort_keys=True,separators=(",",":")).encode()
def derive(shared,a): return HKDF(algorithm=hashes.SHA256(),length=32,salt=hashlib.sha256(a).digest(),info=INFO).derive(shared)

def consume(env_path:Path,response:Path,key_path:Path,run_id:str):
    env=json.loads(env_path.read_text())
    priv=x25519.X25519PrivateKey.from_private_bytes(b64(key_path.read_text().strip()))
    pub=priv.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    key="sha256:"+hashlib.sha256(pub).hexdigest()
    if env.get("schema")!=SCHEMA or str(env.get("run_id"))!=str(run_id) or env.get("harness")!=HARNESS or env.get("mm_commit")!=EXPECTED_MM_COMMIT or env.get("recipient_key_id")!=key: raise RuntimeError("envelope identity mismatch")
    parts=[]
    for item in env.get("chunks") or []:
        raw=(response/Path(item["path"]).name).read_bytes()
        if h(raw)!=item["sha256"] or len(raw.decode("ascii"))!=int(item["chars"]): raise RuntimeError("chunk mismatch")
        parts.append(raw.decode("ascii"))
    cipher=b64("".join(parts))
    if h(cipher)!=env["ciphertext_sha256"]: raise RuntimeError("cipher mismatch")
    associated=aad(run_id,key)
    shared=priv.exchange(x25519.X25519PublicKey.from_public_bytes(b64(env["sender_public_b64"])))
    plain=ChaCha20Poly1305(derive(shared,associated)).decrypt(b64(env["nonce_b64"]),cipher,associated)
    if h(plain)!=env["plaintext_sha256"]: raise RuntimeError("plaintext mismatch")
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); arc=root/"p.tgz"; arc.write_bytes(plain)
        with tarfile.open(arc,"r:gz") as tf: tf.extractall(root)
        manifest=json.loads((root/"payload_manifest.json").read_text())
        identities=[]
        for rel,expected_blob in FILES.items():
            raw=(root/rel).read_bytes()
            identities.append(manifest.get("files",{}).get(rel)==h(raw) and blob(raw)==expected_blob)
        identity=manifest.get("mm_commit")==EXPECTED_MM_COMMIT and set(manifest.get("files",{}))==set(FILES) and all(identities)
        test=subprocess.run([sys.executable,"-m","unittest","tests.test_capital_readiness_panel_completed_trade_evidence_contract"],cwd=root,capture_output=True,text=True)
        ui=(root/"ui-react/src/components/CapitalReadinessPanel.jsx").read_text(encoding="utf-8")
        operator_visible=all(token in ui for token in ["Completed-trade input availability:","intelligence?.completed_trade_evidence","bridge-ready","intent-only","ledger-only","Missing canonical evidence:"])
        fail_closed="Input availability only." in ui and "does not grant trade attribution, Strategy Health readiness, capital authority, or live-trading authority." in ui
    ok=identity and test.returncode==0 and operator_visible and fail_closed
    return {"schema":"mm-completed-trade-evidence-ui-acceptance-receipt-v1","authority":"private_mm_source_validation_only","harness":HARNESS,"mm_commit":EXPECTED_MM_COMMIT,"status":"PASS" if ok else "FAIL","checks":{"reviewed_source_blob_identity_verified":identity,"ui_contract_regressions_pass":test.returncode==0,"completed_trade_availability_operator_visible":operator_visible,"bridge_ready_remains_non_authoritative":fail_closed},"reviewed_source_blob_count":2,"payload_sha256":h(plain),"private_plaintext_emitted":False,"strategy_spec_mutation":False,"runtime_authority_change":False,"broker_submission":False,"live_trading_change":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--envelope",required=True);p.add_argument("--response-dir",required=True);p.add_argument("--private-key",required=True);p.add_argument("--run-id",required=True);a=p.parse_args()
    r=consume(Path(a.envelope),Path(a.response_dir),Path(a.private_key),a.run_id);print("MM_COMPLETED_TRADE_EVIDENCE_UI_RECEIPT="+json.dumps(r,sort_keys=True));raise SystemExit(0 if r["status"]=="PASS" else 1)
if __name__=="__main__": main()
