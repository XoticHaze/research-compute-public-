from __future__ import annotations

import argparse, base64, hashlib, io, json, os, subprocess, tarfile, tempfile
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "p12-review-guard-x25519-v1"
HARNESS = "mm_p12_strategy_builder_review_guard_v1"
INFO = b"commandcenter-p12-review-guard-v1"
SOURCE_PATH = "scripts/operator/strategy_builder_review_guard.py"
TEST_PATH = "tests/test_strategy_builder_review_guard.py"
ALLOWED_FILES = {"manifest.json", SOURCE_PATH, TEST_PATH}
EXPECTED_TEST = "tests.test_strategy_builder_review_guard"


def b64d(v): return base64.b64decode(v.encode("ascii"), validate=True)
def aad(run_id, key_id):
    return json.dumps({"schema":SCHEMA,"run_id":str(run_id),"authority":"research_only","harness":HARNESS,"recipient_key_id":key_id},sort_keys=True,separators=(",",":")).encode()
def derive(shared, a):
    return HKDF(algorithm=hashes.SHA256(),length=32,salt=hashlib.sha256(a).digest(),info=INFO).derive(shared)

def consume(envelope_path: Path, private_key_path: Path, run_id: str):
    env=json.loads(envelope_path.read_text())
    required={"schema","run_id","authority","harness","recipient_key_id","sender_public_b64","nonce_b64","ciphertext_b64","plaintext_sha256"}
    if set(env)!=required or env["schema"]!=SCHEMA or str(env["run_id"])!=str(run_id) or env["harness"]!=HARNESS or env["authority"]!="research_only":
        raise RuntimeError("envelope contract mismatch")
    private=x25519.X25519PrivateKey.from_private_bytes(b64d(private_key_path.read_text().strip()))
    recipient=private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    key_id="sha256:"+hashlib.sha256(recipient).hexdigest()
    if env["recipient_key_id"]!=key_id: raise RuntimeError("recipient key mismatch")
    a=aad(run_id,key_id)
    shared=private.exchange(x25519.X25519PublicKey.from_public_bytes(b64d(env["sender_public_b64"])))
    plaintext=ChaCha20Poly1305(derive(shared,a)).decrypt(b64d(env["nonce_b64"]),b64d(env["ciphertext_b64"]),a)
    psha=hashlib.sha256(plaintext).hexdigest()
    if psha!=env["plaintext_sha256"]: raise RuntimeError("payload digest mismatch")
    with tarfile.open(fileobj=io.BytesIO(plaintext),mode="r:gz") as tf:
        names={m.name for m in tf.getmembers() if m.isfile()}
        if names!=ALLOWED_FILES: raise RuntimeError(f"payload file set mismatch: {sorted(names)}")
        for m in tf.getmembers():
            p=Path(m.name)
            if m.issym() or m.islnk() or p.is_absolute() or ".." in p.parts: raise RuntimeError("unsafe payload member")
        manifest=json.loads(tf.extractfile("manifest.json").read().decode())
        if manifest.get("schema")!="p12-review-guard-payload-v1" or manifest.get("harness")!=HARNESS or manifest.get("authority")!="research_only" or int(manifest.get("mm_pr",0))!=224 or manifest.get("test_module")!=EXPECTED_TEST:
            raise RuntimeError("manifest contract mismatch")
        with tempfile.TemporaryDirectory(prefix="p12-review-guard-") as td:
            root=Path(td); tf.extractall(root)
            (root/"tests").mkdir(parents=True,exist_ok=True); (root/"tests/__init__.py").write_text("")
            (root/"scripts").mkdir(parents=True,exist_ok=True); (root/"scripts/__init__.py").write_text("")
            (root/"scripts/operator").mkdir(parents=True,exist_ok=True); (root/"scripts/operator/__init__.py").write_text("")
            source=(root/SOURCE_PATH).read_bytes(); test=(root/TEST_PATH).read_bytes()
            if hashlib.sha256(source).hexdigest()!=manifest["source_sha256"] or hashlib.sha256(test).hexdigest()!=manifest["test_sha256"]: raise RuntimeError("private source digest mismatch")
            proc=subprocess.run(["python","-m","unittest","-q",EXPECTED_TEST],cwd=root,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
    return {"schema":"p12-review-guard-receipt-v1","authority":"research_only","harness":HARNESS,"mm_pr":224,"mm_head_sha":manifest["mm_head_sha"],"payload_sha256":psha,"test_module":EXPECTED_TEST,"status":"PASS" if proc.returncode==0 else "FAIL","exit_code":proc.returncode,"captured_output_sha256":hashlib.sha256(proc.stdout).hexdigest()}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--envelope",required=True); p.add_argument("--private-key",required=True); p.add_argument("--run-id",required=True); a=p.parse_args()
    receipt=consume(Path(a.envelope),Path(a.private_key),a.run_id); print("P12_REVIEW_GUARD_RECEIPT="+json.dumps(receipt,sort_keys=True)); raise SystemExit(0 if receipt["status"]=="PASS" else 1)
if __name__=="__main__": main()
