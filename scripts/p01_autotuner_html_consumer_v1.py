from __future__ import annotations

import argparse, base64, hashlib, io, json, os, subprocess, tarfile, tempfile
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA='p01-autotuner-html-x25519-v1'
PAYLOAD_SCHEMA='p01-autotuner-html-payload-v1'
RECEIPT_SCHEMA='p01-autotuner-html-receipt-v1'
HARNESS='mm_p01_autotuner_operator_review_html_v1'
AUTHORITY='research_only_operator_review'
MM_HEAD_SHA='b112f6bab2d3bb5f2353e2a502796c8a861c4c7b'
INFO=b'commandcenter-p01-autotuner-html-v1'
SNAPSHOT='input/autotuner-operator-status-snapshot.json'
ENTRYPOINT='scripts/operator/autotuner_operator_status_review_html.mjs'
VIEW_MODEL='ui-react/src/components/autotuner-operator-status-view-model.js'
MAX_FILES=8
MAX_PLAINTEXT_BYTES=4*1024*1024
MAX_MEMBER_BYTES=2*1024*1024


def b64d(v:str)->bytes: return base64.b64decode(v.encode('ascii'),validate=True)
def safe_name(n:str)->bool:
    p=Path(n); return bool(n) and not p.is_absolute() and '..' not in p.parts and '' not in p.parts

def aad(run_id:str,key_id:str)->bytes:
    return json.dumps({'schema':SCHEMA,'run_id':str(run_id),'authority':AUTHORITY,'harness':HARNESS,'recipient_key_id':key_id},sort_keys=True,separators=(',',':')).encode()

def derive(shared:bytes,data:bytes)->bytes:
    return HKDF(algorithm=hashes.SHA256(),length=32,salt=hashlib.sha256(data).digest(),info=INFO).derive(shared)

def reject_authority(v,p='root'):
    if isinstance(v,dict):
        for k,c in v.items():
            key=str(k).strip().lower()
            if key in {'automatic_promotion','automatic_strategy_spec_write','runtime_activation','broker_submit','live_unlock','enable_live_trading','live_trading_enabled'} and c not in (False,None,0,'','false','False'):
                raise RuntimeError(f'forbidden authority at {p}.{k}')
            reject_authority(c,f'{p}.{k}')
    elif isinstance(v,list):
        for i,c in enumerate(v): reject_authority(c,f'{p}[{i}]')

def load_obj(path:Path)->dict:
    v=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(v,dict): raise RuntimeError(f'JSON root must be object: {path}')
    return v

def consume(envelope_path:Path,private_key_path:Path,run_id:str)->dict:
    env=load_obj(envelope_path)
    required={'schema','run_id','authority','harness','recipient_key_id','sender_public_b64','nonce_b64','ciphertext_b64','plaintext_sha256'}
    if set(env)!=required or env['schema']!=SCHEMA or str(env['run_id'])!=str(run_id) or env['authority']!=AUTHORITY or env['harness']!=HARNESS:
        raise RuntimeError('envelope contract mismatch')
    private=x25519.X25519PrivateKey.from_private_bytes(b64d(private_key_path.read_text().strip()))
    recipient_raw=private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    key_id='sha256:'+hashlib.sha256(recipient_raw).hexdigest()
    if env['recipient_key_id']!=key_id: raise RuntimeError('recipient key mismatch')
    data=aad(str(run_id),key_id)
    sender=x25519.X25519PublicKey.from_public_bytes(b64d(env['sender_public_b64']))
    plain=ChaCha20Poly1305(derive(private.exchange(sender),data)).decrypt(b64d(env['nonce_b64']),b64d(env['ciphertext_b64']),data)
    plain_sha=hashlib.sha256(plain).hexdigest()
    if len(plain)>MAX_PLAINTEXT_BYTES or plain_sha!=env['plaintext_sha256']: raise RuntimeError('payload size/digest mismatch')
    with tarfile.open(fileobj=io.BytesIO(plain),mode='r:gz') as ar:
        members=ar.getmembers(); files=[m for m in members if m.isfile()]
        if len(files)>MAX_FILES: raise RuntimeError('payload file count exceeds limit')
        for m in members:
            if m.issym() or m.islnk() or not safe_name(m.name) or (m.isfile() and m.size>MAX_MEMBER_BYTES): raise RuntimeError(f'unsafe payload member: {m.name}')
        names={m.name for m in files}
        if 'manifest.json' not in names: raise RuntimeError('manifest missing')
        manifest=json.loads(ar.extractfile('manifest.json').read().decode())
        if manifest.get('schema')!=PAYLOAD_SCHEMA or manifest.get('harness')!=HARNESS or manifest.get('authority')!=AUTHORITY or manifest.get('mm_head_sha')!=MM_HEAD_SHA or manifest.get('entrypoint')!=ENTRYPOINT or manifest.get('snapshot')!=SNAPSHOT:
            raise RuntimeError('manifest contract mismatch')
        declared=manifest.get('file_sha256')
        required_files={ENTRYPOINT,VIEW_MODEL,SNAPSHOT}
        if not isinstance(declared,dict) or names!=set(declared)|{'manifest.json'} or not required_files.issubset(names): raise RuntimeError('payload file-set mismatch')
        with tempfile.TemporaryDirectory(prefix='p01-autotuner-html-') as td:
            root=Path(td); ar.extractall(root)
            for rel,expected in declared.items():
                if not safe_name(rel) or hashlib.sha256((root/rel).read_bytes()).hexdigest()!=str(expected).lower(): raise RuntimeError(f'payload digest mismatch: {rel}')
            snapshot=load_obj(root/SNAPSHOT)
            if snapshot.get('schema')!='mm.autotuner_operator_status_snapshot.v1': raise RuntimeError('snapshot schema mismatch')
            if int(snapshot.get('runtime_count') or 0)<1 or len(snapshot.get('runtimes') or [])!=int(snapshot['runtime_count']): raise RuntimeError('snapshot runtime count invalid')
            reject_authority(snapshot)
            out=root/'autotuner-operator-review.html'
            proc=subprocess.run(['node',ENTRYPOINT,SNAPSHOT,str(out)],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
            if proc.returncode!=0 or not out.is_file(): raise RuntimeError('HTML consumer execution failed: '+hashlib.sha256(proc.stdout).hexdigest())
            html=out.read_bytes()
            if b'Fail-closed authority boundary' not in html or b'Automatic promotion: false' not in html: raise RuntimeError('HTML safety presentation missing')
            return {'schema':RECEIPT_SCHEMA,'authority':AUTHORITY,'harness':HARNESS,'mm_head_sha':MM_HEAD_SHA,'status':'PASS','runtime_count':int(snapshot['runtime_count']),'snapshot_sha256':hashlib.sha256((root/SNAPSHOT).read_bytes()).hexdigest(),'html_sha256':hashlib.sha256(html).hexdigest(),'automatic_promotion':False,'strategy_spec_write':False,'runtime_activation':False,'broker_submit':False,'live_unlock':False}

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('--envelope',type=Path,required=True); p.add_argument('--private-key',type=Path,required=True); p.add_argument('--run-id',required=True); a=p.parse_args()
    print('P01_AUTOTUNER_HTML_RECEIPT='+json.dumps(consume(a.envelope,a.private_key,a.run_id),sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
