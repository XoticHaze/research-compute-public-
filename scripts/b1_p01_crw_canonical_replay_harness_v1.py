from __future__ import annotations
import base64,gzip,hashlib,json,os,shutil,subprocess,tarfile,time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl,urlencode,urlparse,urlunparse
from urllib.request import Request,urlopen
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SOURCE='553197599239f1efd0a302642872a5a064a1da32'
WORKLOAD='df215b2b6c8bc0ba2b6652e010862e789dbe2c4c'
CORPUS_SHA='c04a95debfde500aa245d187a1d30620a88703113013a63af0c3553b0509e44e'
CORPUS_BYTES=18026715
HARNESS='b1_p01_crw_canonical_replay_r1'
BASE='https://fleet-authority.slenderiq.workers.dev'
EXCHANGE='rendezvous-exchange'

def get_json(url,headers=None,timeout=30):
    with urlopen(Request(url,headers=headers or {}),timeout=timeout) as r:return json.load(r)
def oidc():
    p=urlparse(os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']);q=dict(parse_qsl(p.query,keep_blank_values=True));q['audience']='mmibkr-fleet-authority';u=urlunparse((p.scheme,p.netloc,p.path,p.params,urlencode(q),p.fragment));d=get_json(u,{'Authorization':'Bearer '+os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN'],'Accept':'application/json'});t=str(d.get('value') or '')
    if t.count('.')!=2:raise RuntimeError('oidc invalid')
    return t
def gh_put(path,data,message):
    body=json.dumps({'message':message,'content':base64.b64encode(data).decode(),'branch':EXCHANGE},separators=(',',':')).encode();u=f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/contents/{path}";req=Request(u,data=body,method='PUT',headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','Content-Type':'application/json'})
    with urlopen(req,timeout=30) as r:return json.load(r)
def gh_raw(path):
    u=f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/contents/{path}?ref={EXCHANGE}";req=Request(u,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github.raw+json'})
    with urlopen(req,timeout=30) as r:return r.read()
def safe_extract(archive,dest):
    with tarfile.open(archive,'r:gz') as tf:
        ms=tf.getmembers();tops={Path(m.name).parts[0] for m in ms if Path(m.name).parts}
        if len(tops)!=1:raise RuntimeError('archive root rejected')
        root=(dest/next(iter(tops))).resolve()
        for m in ms:
            p=Path(m.name);target=(dest/p).resolve()
            if p.is_absolute() or '..' in p.parts or m.issym() or m.islnk() or m.isdev() or (target!=root and root not in target.parents):raise RuntimeError('unsafe archive')
            if m.isdir():target.mkdir(parents=True,exist_ok=True);continue
            if not m.isfile():raise RuntimeError('archive member rejected')
            h=tf.extractfile(m)
            if h is None:raise RuntimeError('archive member unreadable')
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('wb') as out:shutil.copyfileobj(h,out,1024*1024)
        return root

def main():
    run=os.environ['GITHUB_RUN_ID'];temp=Path(os.environ['RUNNER_TEMP']);archive=temp/'source.tar.gz';dest=temp/'source';headers={'Authorization':'Bearer '+oidc(),'Accept':'application/gzip','User-Agent':'b1-p01-crw-canonical-replay-r1','X-MMIBKR-Caller-Run-Id':run};url=f'{BASE}/v1/source-vault/private-archive/{SOURCE}';rh=None
    for _ in range(72):
        try:
            with urlopen(Request(url,headers=headers),timeout=60) as r:
                rh=dict(r.headers.items())
                with archive.open('wb') as out:shutil.copyfileobj(r,out,1024*1024)
            break
        except HTTPError as e:
            if e.code not in {401,403,502,503}:raise
            time.sleep(5)
    else:raise RuntimeError('source admission timeout')
    n={str(k).lower():str(v) for k,v in (rh or {}).items()}
    if n.get('x-mmibkr-source-sha')!=SOURCE or n.get('x-mmibkr-private-source-token-exposed')!='false':raise RuntimeError('source identity rejected')
    stream=n.get('x-mmibkr-source-stream-id','');digest=hashlib.sha256(archive.read_bytes()).hexdigest();size=archive.stat().st_size;att={'schema':'mmibkr-fleet-private-source-attest-v1','source_sha':SOURCE,'stream_id':stream,'archive_sha256':digest,'archive_bytes':size};req=Request(BASE+'/v1/source-vault/private-archive/attest',data=json.dumps(att,sort_keys=True,separators=(',',':')).encode(),method='POST',headers={'Authorization':'Bearer '+oidc(),'Accept':'application/json','Content-Type':'application/json','User-Agent':'b1-p01-crw-canonical-replay-r1','X-MMIBKR-Caller-Run-Id':run})
    with urlopen(req,timeout=30) as r:a=json.load(r)
    if a.get('ok') is not True or a.get('source_sha')!=SOURCE:raise RuntimeError('source attestation failed')
    root=safe_extract(archive,dest);w=root/'scripts/operator/crw_backtest_summary_13z.py'
    if hashlib.sha1(w.read_bytes()).hexdigest()!=WORKLOAD:raise RuntimeError('canonical workload mismatch')
    print('B1_PRIVATE_SOURCE_SHA='+SOURCE);print('B1_CRW_WORKLOAD_BLOB_SHA1='+WORKLOAD);print('B1_PRIVATE_SOURCE_TOKEN_EXPOSED=0')
    key=x25519.X25519PrivateKey.generate();priv=key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption());pub=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw);kid='sha256:'+hashlib.sha256(pub).hexdigest();recipient={'schema':'b1-p01-crw-recipient-v1','run_id':run,'recipient_b64':base64.b64encode(pub).decode(),'recipient_key_id':kid,'corpus_sha256':CORPUS_SHA,'corpus_bytes':CORPUS_BYTES};recipient_path=f'rendezvous/recipients/{run}-b1-p01-crw.json';gh_put(recipient_path,(json.dumps(recipient,sort_keys=True)+'\n').encode(),'rendezvous: publish B1 P01 CRW recipient');print('B1_RECIPIENT_PATH='+recipient_path)
    response_root=f'rendezvous/responses/{run}/b1-p01-crw';envelope=None
    for _ in range(300):
        try:envelope=json.loads(gh_raw(response_root+'/envelope.json'));break
        except HTTPError as e:
            if e.code!=404:raise
            time.sleep(5)
    if envelope is None:raise RuntimeError('encrypted corpus envelope timeout')
    if envelope.get('schema')!='b1-p01-crw-ephemeral-x25519-v1' or str(envelope.get('run_id'))!=run or envelope.get('harness')!=HARNESS or envelope.get('recipient_key_id')!=kid:raise RuntimeError('envelope rejected')
    parts=[]
    for node in envelope['chunks']:
        p=node['path']
        if not p.startswith(response_root+'/'):raise RuntimeError('chunk path rejected')
        raw=gh_raw(p)
        if hashlib.sha256(raw).hexdigest()!=node['sha256'] or len(raw)!=int(node['chars']):raise RuntimeError('chunk mismatch')
        parts.append(raw.decode())
    ct=base64.b64decode(''.join(parts),validate=True)
    if hashlib.sha256(ct).hexdigest()!=envelope['ciphertext_sha256']:raise RuntimeError('ciphertext mismatch')
    sender=x25519.X25519PublicKey.from_public_bytes(base64.b64decode(envelope['sender_public_b64'],validate=True));shared=key.exchange(sender);derived=HKDF(algorithm=hashes.SHA256(),length=32,salt=None,info=(HARNESS+':'+run).encode()).derive(shared);nonce=base64.b64decode(envelope['nonce_b64'],validate=True);aad=(HARNESS+':'+run+':'+CORPUS_SHA).encode();plain=gzip.decompress(ChaCha20Poly1305(derived).decrypt(nonce,ct,aad))
    if hashlib.sha256(plain).hexdigest()!=CORPUS_SHA or len(plain)!=CORPUS_BYTES:raise RuntimeError('corpus identity mismatch')
    corpus=temp/'corpus.csv';corpus.write_bytes(plain);print('B1_CORPUS_SHA256='+CORPUS_SHA);print('B1_CORPUS_BYTES='+str(CORPUS_BYTES))
    build=temp/'build.log';cmd=['docker','build','-f',str(root/'Dockerfile.bot'),'--target','bot','-t',f'b1-crw:{run}',str(root)]
    with build.open('wb') as out:r=subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT)
    print('B1_BUILD_LOG_SHA256='+hashlib.sha256(build.read_bytes()).hexdigest())
    if r.returncode:raise RuntimeError('private source image build failed')
    request={'strategy_id':'crw_score_multi_mode','symbols':['MNQ'],'timeframe':'12Min','asset_type':'futures','params':{'STRATEGY_TYPE':'Extreme','SCORE_TYPE':'Classic Z','WINDOW':96,'ENTRY_EXTREME':-2.52,'EXIT_EXTREME':4.5,'ENABLE_LONGS':True,'DCA_ENABLED':False,'commission_per_share':0.0,'min_commission':0.0,'slippage_bps':0.0,'spread_bps':0.0,'session_filter_applied':False},'_verified_source_paths':{'MNQ':'/exchange/corpus.csv'},'paper_only':True,'live_allowed':False};req=temp/'request.json';req.write_text(json.dumps(request));result=temp/'replay.json';cmd=['docker','run','--rm','-e','ENABLE_LIVE_TRADING=0','-v',f'{temp}:/exchange:ro',f'b1-crw:{run}','python','-m','scripts.operator.crw_backtest_summary_13z','--request-json','/exchange/request.json']
    with result.open('wb') as out:r=subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT)
    if r.returncode:print('B1_REPLAY_LOG_SHA256='+hashlib.sha256(result.read_bytes()).hexdigest());raise RuntimeError('canonical replay failed')
    data=json.loads(result.read_text());receipt={'schema':'b1-p01-crw-canonical-replay-receipt-v1','run_id':run,'public_head':os.environ['GITHUB_SHA'],'private_source_sha':SOURCE,'workload_blob_sha1':WORKLOAD,'corpus_sha256':CORPUS_SHA,'corpus_bytes':CORPUS_BYTES,'parameters':{'symbol':'MNQ','timeframe':'12Min','window':96,'entry_extreme':-2.52,'exit_extreme':4.5,'dca_enabled':False},'terminal_status':data.get('status'),'ok':data.get('ok'),'total_trades':data.get('total_trades'),'net_pnl':data.get('net_pnl'),'profit_factor':data.get('profit_factor'),'max_drawdown':data.get('max_drawdown'),'data_coverage':data.get('data_coverage'),'raw_result_sha256':hashlib.sha256(result.read_bytes()).hexdigest(),'raw_result_bytes':result.stat().st_size,'protected_holdout_read':False};out=Path('b1-p01-crw-canonical-replay-receipt.json');out.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n');print('B1_CANONICAL_REPLAY_STATUS='+str(receipt['terminal_status']));print('B1_CANONICAL_REPLAY_OK='+str(receipt['ok']).lower());print('B1_SANITIZED_RECEIPT_SHA256='+hashlib.sha256(out.read_bytes()).hexdigest())
if __name__=='__main__':main()
