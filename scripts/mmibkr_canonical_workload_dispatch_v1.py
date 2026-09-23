from __future__ import annotations
"""Portable fail-closed dispatcher for allowlisted MM-IBKR research work."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib, importlib, json, os, re, secrets, sys, threading, time
from pathlib import Path
from typing import Any

REQUEST_SCHEMA="mmibkr.canonical_workload_request.v1"
PLAN_SCHEMA="mmibkr.canonical_workload_plan.v1"
RECEIPT_SCHEMA="mmibkr.canonical_workload_receipt.v1"
PLAN_RECEIPT_SCHEMA="mmibkr.canonical_workload_plan_receipt.v1"
CLAIM_SCHEMA="mmibkr.canonical_workload_claim.v1"
CLAIM_LEASE_SECONDS=120
CLAIM_HEARTBEAT_SECONDS=30
SOURCE_RECEIPT_SCHEMA="mmibkr.private_source_materialization.v1"
SOURCE_REPOSITORY="XoticHaze/mm-IBKR"
AUTHORITY="research_only"
FORBIDDEN_AUTHORITY_KEYS=("broker_submit","broker_cancel","broker_flatten","strategy_spec_write","runtime_activation","promotion_mutation","live_trading")
FORBIDDEN_AUTHORITY_ASSERTIONS={k:False for k in FORBIDDEN_AUTHORITY_KEYS}
CAPABILITIES={"STRATEGY_SPEC_VALIDATE":{"path":"autotuner_strategy_bridge.py","module":"autotuner_strategy_bridge","callable":"normalize_strategy_spec"}}
_SHA1=re.compile(r"^[0-9a-f]{40}$"); _SHA256=re.compile(r"^[0-9a-f]{64}$"); _ID=re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_IMPORT_LOCK=threading.Lock()

class CanonicalDispatchError(RuntimeError): pass

def cbytes(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False,default=str).encode()
def sha(v:Any)->str:return hashlib.sha256(cbytes(v)).hexdigest()
def git_blob(raw:bytes)->str:return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
def load(path:Path)->dict:
    try:v=json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:raise CanonicalDispatchError(f"invalid JSON: {path}: {e}") from e
    if not isinstance(v,dict):raise CanonicalDispatchError(f"JSON root must be object: {path}")
    return v
def exact(v:dict,keys:set[str],label:str):
    extra=set(v)-keys
    if extra:raise CanonicalDispatchError(f"{label} unexpected fields={sorted(extra)}")
def valid_id(v:Any,label="job_id"):
    s=str(v or "").strip()
    if not _ID.fullmatch(s):raise CanonicalDispatchError(f"{label} is invalid")
    return s

def resources(v:Any):
    if not isinstance(v,dict):raise CanonicalDispatchError("resources must be object")
    exact(v,{"max_wall_seconds","max_output_bytes"},"resources")
    try:w=int(v.get("max_wall_seconds",60));o=int(v.get("max_output_bytes",1_000_000))
    except Exception as e:raise CanonicalDispatchError("resource bounds must be integers") from e
    if not 1<=w<=18000:raise CanonicalDispatchError("max_wall_seconds must be within 1..18000")
    if not 1024<=o<=10_000_000:raise CanonicalDispatchError("max_output_bytes must be within 1024..10000000")
    return {"max_wall_seconds":w,"max_output_bytes":o}

def validate_source(receipt:dict,root:Path,mm:dict):
    if receipt.get("schema")!=SOURCE_RECEIPT_SCHEMA:raise CanonicalDispatchError("unsupported private source receipt schema")
    if receipt.get("mmibkr_repository")!=SOURCE_REPOSITORY:raise CanonicalDispatchError("private source repository mismatch")
    if receipt.get("mmibkr_head")!=mm["commit"]:raise CanonicalDispatchError("private source commit mismatch")
    if receipt.get("source_archive_sha256")!=mm["source_archive_sha256"]:raise CanonicalDispatchError("private source archive digest mismatch")
    for k in ("broker_credentials_materialized","tws_credentials_required","source_token_emitted","paper_or_live_authority"):
        if receipt.get(k) is not False:raise CanonicalDispatchError(f"private source receipt must assert {k}=false")
    if Path(str(receipt.get("source_root") or "")).resolve()!=root.resolve():raise CanonicalDispatchError("private source root mismatch")
    if not root.is_dir():raise CanonicalDispatchError("private source root does not exist")

def validate_request(req:dict,root:Path,source_receipt:dict)->dict:
    exact(req,{"schema","job_id","capability_id","mmibkr","entrypoint","arguments","resources","authority","forbidden_authorities"},"request")
    if req.get("schema")!=REQUEST_SCHEMA:raise CanonicalDispatchError("unsupported request schema")
    jid=valid_id(req.get("job_id")); cid=str(req.get("capability_id") or "").strip(); cap=CAPABILITIES.get(cid)
    if not cap:raise CanonicalDispatchError(f"capability is not allowlisted: {cid!r}")
    if req.get("authority")!=AUTHORITY:raise CanonicalDispatchError("authority must be research_only")
    if req.get("forbidden_authorities")!=FORBIDDEN_AUTHORITY_ASSERTIONS:raise CanonicalDispatchError("forbidden authority assertions must all be false")
    mm=req.get("mmibkr")
    if not isinstance(mm,dict):raise CanonicalDispatchError("mmibkr must be object")
    exact(mm,{"repository","commit","source_archive_sha256"},"mmibkr")
    commit=str(mm.get("commit") or "").lower(); archive=str(mm.get("source_archive_sha256") or "").lower()
    if mm.get("repository")!=SOURCE_REPOSITORY:raise CanonicalDispatchError("MM-IBKR repository identity mismatch")
    if not _SHA1.fullmatch(commit):raise CanonicalDispatchError("MM-IBKR commit must be lowercase 40-hex SHA")
    if not _SHA256.fullmatch(archive):raise CanonicalDispatchError("source_archive_sha256 must be lowercase 64-hex SHA")
    mm={"repository":SOURCE_REPOSITORY,"commit":commit,"source_archive_sha256":archive}; validate_source(source_receipt,root,mm)
    ep=req.get("entrypoint")
    if not isinstance(ep,dict):raise CanonicalDispatchError("entrypoint must be object")
    exact(ep,{"path","module","callable","git_blob_sha1"},"entrypoint")
    for k in ("path","module","callable"):
        if str(ep.get(k) or "")!=cap[k]:raise CanonicalDispatchError(f"entrypoint {k} does not match capability registry")
    expected=str(ep.get("git_blob_sha1") or "").lower()
    if not _SHA1.fullmatch(expected):raise CanonicalDispatchError("entrypoint git_blob_sha1 is invalid")
    p=(root/cap["path"]).resolve()
    if root.resolve() not in p.parents or not p.is_file():raise CanonicalDispatchError("canonical entrypoint file is missing or outside source root")
    actual=git_blob(p.read_bytes())
    if actual!=expected:raise CanonicalDispatchError(f"canonical entrypoint blob mismatch expected={expected} actual={actual}")
    args=req.get("arguments")
    if cid=="STRATEGY_SPEC_VALIDATE" and (not isinstance(args,dict) or set(args)!={"strategy_spec"} or not isinstance(args.get("strategy_spec"),dict)):
        raise CanonicalDispatchError("STRATEGY_SPEC_VALIDATE arguments must contain only strategy_spec object")
    return {"schema":REQUEST_SCHEMA,"job_id":jid,"capability_id":cid,"mmibkr":mm,"entrypoint":{**cap,"git_blob_sha1":actual},"arguments":args,"resources":resources(req.get("resources")),"authority":AUTHORITY,"forbidden_authorities":dict(FORBIDDEN_AUTHORITY_ASSERTIONS)}

def load_callable(root:Path,cap:dict):
    want=(root/cap["path"]).resolve(); rp=str(root.resolve())
    with _IMPORT_LOCK:
        old=sys.modules.get(cap["module"])
        if old is not None and Path(str(getattr(old,"__file__","") or "")).resolve()!=want:del sys.modules[cap["module"]]
        importlib.invalidate_caches(); added=rp not in sys.path
        if added:sys.path.insert(0,rp)
        try:m=importlib.import_module(cap["module"])
        finally:
            if added and rp in sys.path:sys.path.remove(rp)
        if Path(str(getattr(m,"__file__","") or "")).resolve()!=want:raise CanonicalDispatchError("imported module path does not match verified entrypoint")
        fn=getattr(m,cap["callable"],None)
        if not callable(fn):raise CanonicalDispatchError("canonical callable missing")
        return fn

def execute_valid(v:dict,root:Path)->dict:
    fn=load_callable(root,CAPABILITIES[v["capability_id"]]); raw=fn(v["arguments"]["strategy_spec"])
    if not isinstance(raw,dict) or not isinstance(raw.get("strategy_spec"),dict) or not _SHA256.fullmatch(str(raw.get("strategy_spec_digest") or "")):
        raise CanonicalDispatchError("canonical StrategySpec validator returned invalid contract")
    result={"strategy_spec":raw["strategy_spec"],"strategy_spec_digest":raw["strategy_spec_digest"]}
    rb=cbytes(result)
    if len(rb)>v["resources"]["max_output_bytes"]:raise CanonicalDispatchError("canonical result exceeded max_output_bytes")
    fp=sha(v)
    return {"schema":RECEIPT_SCHEMA,"job_id":v["job_id"],"job_fingerprint":fp,"capability_id":v["capability_id"],"status":"completed","authority":{"research_only":True,**FORBIDDEN_AUTHORITY_ASSERTIONS},"mmibkr":v["mmibkr"],"entrypoint":v["entrypoint"],"resources":v["resources"],"result_sha256":hashlib.sha256(rb).hexdigest(),"result":result}

def atomic(path:Path,v:dict):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"); tmp.write_bytes(cbytes(v)+b"\n"); os.replace(tmp,path)
def cached(path:Path,fp:str):
    if not path.is_file():return None
    r=load(path)
    if r.get("schema")!=RECEIPT_SCHEMA or r.get("job_fingerprint")!=fp or r.get("status")!="completed":raise CanonicalDispatchError("cached receipt identity/status mismatch")
    return r

def claim_owned(path:Path,token:str,fp:str)->bool:
    try:
        node=load(path)
    except Exception:
        return False
    return (
        node.get("schema")==CLAIM_SCHEMA
        and node.get("claim_token")==token
        and node.get("job_fingerprint")==fp
    )

def acquire_claim(path:Path,v:dict,fp:str,receipt_path:Path)->tuple[str,dict|None]:
    path.parent.mkdir(parents=True,exist_ok=True)
    stale_dir=path.parent/"stale"; stale_dir.mkdir(parents=True,exist_ok=True)
    while True:
        token=secrets.token_hex(16)
        payload={
            "schema":CLAIM_SCHEMA,
            "job_id":v["job_id"],
            "job_fingerprint":fp,
            "claim_token":token,
            "pid":os.getpid(),
            "lease_seconds":CLAIM_LEASE_SECONDS,
            "claimed_at_epoch":time.time(),
        }
        try:
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        except FileExistsError:
            hit=cached(receipt_path,fp)
            if hit:return "",hit
            try:
                node=load(path); stat=path.stat()
            except FileNotFoundError:
                continue
            except Exception as e:
                raise CanonicalDispatchError("existing claim is malformed") from e
            if node.get("schema")!=CLAIM_SCHEMA or node.get("job_fingerprint")!=fp:
                raise CanonicalDispatchError("existing claim identity mismatch")
            try:lease=max(1,int(node.get("lease_seconds") or CLAIM_LEASE_SECONDS))
            except Exception as e:raise CanonicalDispatchError("existing claim lease is invalid") from e
            age=max(0.0,time.time()-stat.st_mtime)
            if age<=lease:
                raise CanonicalDispatchError("job is already claimed and lease is active")
            stale=stale_dir/f"{fp}.{int(time.time())}.{secrets.token_hex(4)}.claim"
            try:os.replace(path,stale)
            except FileNotFoundError:continue
            continue
        with os.fdopen(fd,"w") as h:
            h.write(json.dumps(payload,sort_keys=True)+"\n")
        return token,None

def start_claim_heartbeat(path:Path,token:str,fp:str)->tuple[threading.Event,threading.Event,threading.Thread]:
    stop=threading.Event(); lost=threading.Event()
    def beat():
        while not stop.wait(CLAIM_HEARTBEAT_SECONDS):
            if not claim_owned(path,token,fp):
                lost.set();return
            try:os.utime(path,None)
            except FileNotFoundError:
                lost.set();return
    thread=threading.Thread(target=beat,name=f"mmibkr-claim-{fp[:8]}",daemon=True);thread.start()
    return stop,lost,thread

def execute_request(req:dict,*,source_root:Path,source_receipt:dict,receipt_dir:Path|None=None)->dict:
    v=validate_request(req,source_root,source_receipt); fp=sha(v)
    if receipt_dir is None:return {"receipt":execute_valid(v,source_root),"cache_hit":False}
    rd=receipt_dir.resolve(); rp=rd/"receipts"/f"{fp}.json"; hit=cached(rp,fp)
    if hit:return {"receipt":hit,"cache_hit":True}
    cp=rd/"claims"/f"{fp}.claim"
    token,hit=acquire_claim(cp,v,fp,rp)
    if hit:return {"receipt":hit,"cache_hit":True}
    stop,lost,thread=start_claim_heartbeat(cp,token,fp)
    published=False
    try:
        r=execute_valid(v,source_root)
        if lost.is_set() or not claim_owned(cp,token,fp):
            raise CanonicalDispatchError("claim lease ownership was lost; canonical result discarded")
        atomic(rp,r);published=True;return {"receipt":r,"cache_hit":False}
    finally:
        stop.set();thread.join(timeout=1)
        if claim_owned(cp,token,fp):cp.unlink(missing_ok=True)

def validate_plan(plan:dict)->dict:
    exact(plan,{"schema","plan_id","max_parallel","jobs"},"plan")
    if plan.get("schema")!=PLAN_SCHEMA:raise CanonicalDispatchError("unsupported plan schema")
    pid=valid_id(plan.get("plan_id"),"plan_id")
    try:mp=int(plan.get("max_parallel",1))
    except Exception as e:raise CanonicalDispatchError("max_parallel must be integer") from e
    if not 1<=mp<=8:raise CanonicalDispatchError("max_parallel must be within 1..8")
    jobs=plan.get("jobs")
    if not isinstance(jobs,list) or not jobs or len(jobs)>256:raise CanonicalDispatchError("plan jobs must contain 1..256 jobs")
    norm=[]; ids=set()
    for n in jobs:
        if not isinstance(n,dict):raise CanonicalDispatchError("plan job node must be object")
        exact(n,{"job_id","depends_on","request"},"plan job"); jid=valid_id(n.get("job_id")); deps=n.get("depends_on"); req=n.get("request")
        if jid in ids:raise CanonicalDispatchError(f"duplicate plan job_id: {jid}")
        if not isinstance(deps,list) or any(not isinstance(x,str) for x in deps) or len(deps)!=len(set(deps)):raise CanonicalDispatchError(f"invalid depends_on: {jid}")
        if not isinstance(req,dict) or req.get("job_id")!=jid:raise CanonicalDispatchError(f"plan/request job_id mismatch: {jid}")
        ids.add(jid); norm.append({"job_id":jid,"depends_on":deps,"request":req})
    for n in norm:
        for d in n["depends_on"]:
            if d not in ids or d==n["job_id"]:raise CanonicalDispatchError(f"invalid dependency {d!r} for {n['job_id']}")
    rem={n["job_id"]:set(n["depends_on"]) for n in norm}; done=set()
    while rem:
        ready=[j for j,d in rem.items() if d<=done]
        if not ready:raise CanonicalDispatchError("plan dependency graph contains a cycle")
        for j in ready:rem.pop(j);done.add(j)
    return {"schema":PLAN_SCHEMA,"plan_id":pid,"max_parallel":mp,"jobs":norm}

def execute_plan(plan:dict,*,source_root:Path,source_receipt:dict,receipt_dir:Path)->dict:
    p=validate_plan(plan); pending={n["job_id"]:n for n in p["jobs"]}; states={}; waves=[]
    while pending:
        failed={j for j,s in states.items() if s["state"]=="failed"}
        for j in list(pending):
            bad=[d for d in pending[j]["depends_on"] if d in failed]
            if bad:states[j]={"state":"blocked","blocked_by":bad,"cache_hit":False};pending.pop(j)
        if not pending:break
        good={j for j,s in states.items() if s["state"] in {"completed","cached"}}
        ready=sorted(j for j,n in pending.items() if set(n["depends_on"])<=good); waves.append(ready)
        if not ready:break
        def run(j):
            try:
                x=execute_request(pending[j]["request"],source_root=source_root,source_receipt=source_receipt,receipt_dir=receipt_dir);r=x["receipt"]
                return j,{"state":"cached" if x["cache_hit"] else "completed","cache_hit":x["cache_hit"],"job_fingerprint":r["job_fingerprint"],"receipt_sha256":sha(r)}
            except Exception as e:return j,{"state":"failed","cache_hit":False,"error":str(e)}
        with ThreadPoolExecutor(max_workers=min(p["max_parallel"],len(ready))) as pool:
            for f in as_completed([pool.submit(run,j) for j in ready]):
                j,s=f.result();states[j]=s;pending.pop(j,None)
    status="completed" if states and all(s["state"] in {"completed","cached"} for s in states.values()) else "failed"
    out={"schema":PLAN_RECEIPT_SCHEMA,"plan_id":p["plan_id"],"status":status,"max_parallel":p["max_parallel"],"waves":waves,"jobs":{j:states[j] for j in sorted(states)},"authority":{"research_only":True,**FORBIDDEN_AUTHORITY_ASSERTIONS}}
    atomic(receipt_dir/f"plan-{p['plan_id']}.json",out);return out

def main()->int:
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest="cmd",required=True)
    for name in ("run","plan-run"):
        q=sub.add_parser(name);q.add_argument("--source-root",required=True);q.add_argument("--source-receipt",required=True);q.add_argument("--receipt-dir",required=name=="plan-run");q.add_argument("--request" if name=="run" else "--plan",required=True)
    a=ap.parse_args();root=Path(a.source_root).resolve();sr=load(Path(a.source_receipt));rd=Path(a.receipt_dir).resolve() if a.receipt_dir else None
    try:
        out=execute_request(load(Path(a.request)),source_root=root,source_receipt=sr,receipt_dir=rd) if a.cmd=="run" else execute_plan(load(Path(a.plan)),source_root=root,source_receipt=sr,receipt_dir=rd)
        print(json.dumps(out,sort_keys=True));return 0
    except CanonicalDispatchError as e:print(json.dumps({"ok":False,"error":str(e)},sort_keys=True),file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())
