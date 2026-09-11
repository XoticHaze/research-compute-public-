from __future__ import annotations

import argparse,base64,hashlib,json,subprocess,sys,tarfile,tempfile,types
from pathlib import Path
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA="mm-survivor-forward-x25519-v1"
HARNESS="mm_strategy_health_preview_availability_acceptance_v1"
INFO=b"commandcenter-mm-survivor-forward-v1"
EXPECTED_MM_COMMIT="0dc5e18c2a0a0620147988a7de9239d4d53d874c"
REL="strategy_health_preview_binding.py"
EXPECTED_BLOB="8cb6f6f813db1e1d1e62935c2c6f7e6090a6e039"

def h(b): return hashlib.sha256(b).hexdigest()
def b64(v): return base64.b64decode(v.encode("ascii"),validate=True)
def blob(raw): return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()
def aad(run,key): return json.dumps({"schema":SCHEMA,"run_id":str(run),"harness":HARNESS,"mm_commit":EXPECTED_MM_COMMIT,"recipient_key_id":key},sort_keys=True,separators=(",",":")).encode()
def derive(shared,a): return HKDF(algorithm=hashes.SHA256(),length=32,salt=hashlib.sha256(a).digest(),info=INFO).derive(shared)

def seam_test(path:Path):
    seen={}
    def build(preview,trades,as_of,evidence_availability=None):
        seen["availability"]=evidence_availability
        return {"evidence_state":"INSUFFICIENT_EVIDENCE","completed_trade_evidence":{"state":"BRIDGE_READY" if evidence_availability else "UNKNOWN"}}
    stubs={
      "strategy_capital_readiness":("project_survivor_capital_readiness",lambda *a,**k:{}),
      "strategy_forward_identity_evidence":("project_forward_identity_evidence",lambda *a,**k:{}),
      "strategy_forward_intelligence":("project_survivor_forward_intelligence",lambda *a,**k:{}),
      "strategy_health_comparable_context":("project_comparable_state_context",lambda *a,**k:{}),
      "strategy_health_evidence_pipeline":("build_strategy_health_evidence",build),
      "strategy_health_operator_context":("project_strategy_health_operator_context",lambda *a,**k:{}),
      "strategy_health_position_context":("project_position_duration_context",lambda *a,**k:{}),
      "survivor_capital_readiness_policy":("policy_for",lambda *a,**k:None),
    }
    for name,(attr,fn) in stubs.items():
        mod=types.ModuleType(name); setattr(mod,attr,fn); sys.modules[name]=mod
    ns={"__name__":"preview_binding_acceptance"}
    exec(compile(path.read_text(encoding="utf-8"),str(path),"exec"),ns)
    availability={"schema":"mm.survivor_run_data_availability_audit.v1","symbols":{"MNQ":{"bridge_ready_runs":1}}}
    preview={"strategy_id":"crw_score_multi_mode","symbol":"MNQ","timeframe":"12Min"}
    bound=ns["bind_strategy_health_to_preview"](preview,[],"2026-09-11T00:00:00Z",evidence_availability=availability)
    return seen.get("availability") is availability and bound["strategy_health"]["completed_trade_evidence"]["state"]=="BRIDGE_READY" and bound["strategy_health"]["evidence_state"]=="INSUFFICIENT_EVIDENCE"

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
        raw=(root/REL).read_bytes()
        identity=manifest.get("mm_commit")==EXPECTED_MM_COMMIT and set((manifest.get("files") or {}))=={REL} and h(raw)==manifest["files"][REL] and blob(raw)==EXPECTED_BLOB
        compile_ok=subprocess.run(["python","-m","py_compile",REL],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
        seam_ok=seam_test(root/REL)
    ok=identity and compile_ok and seam_ok
    return {"schema":"mm-strategy-health-preview-availability-acceptance-receipt-v1","authority":"private_mm_source_validation_only","harness":HARNESS,"mm_commit":EXPECTED_MM_COMMIT,"status":"PASS" if ok else "FAIL","checks":{"reviewed_source_blob_identity_verified":identity,"preview_binding_compiles":compile_ok,"availability_forwarding_seam_pass":seam_ok,"bridge_ready_does_not_promote_health":seam_ok},"reviewed_source_blob_count":1,"payload_sha256":h(plain),"private_plaintext_emitted":False,"strategy_spec_mutation":False,"runtime_authority_change":False,"broker_submission":False,"live_trading_change":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--envelope",required=True);p.add_argument("--response-dir",required=True);p.add_argument("--private-key",required=True);p.add_argument("--run-id",required=True);a=p.parse_args()
    r=consume(Path(a.envelope),Path(a.response_dir),Path(a.private_key),a.run_id);print("MM_STRATEGY_HEALTH_PREVIEW_AVAILABILITY_RECEIPT="+json.dumps(r,sort_keys=True));raise SystemExit(0 if r["status"]=="PASS" else 1)
if __name__=="__main__": main()
