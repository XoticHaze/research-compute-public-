from __future__ import annotations
"""Portable fail-closed dispatcher for allowlisted MM-IBKR research work."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import hashlib, importlib, json, os, re, secrets, shutil, sys, threading, time
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
CAPABILITIES={
    "STRATEGY_SPEC_VALIDATE":{
        "path":"autotuner_strategy_bridge.py",
        "module":"autotuner_strategy_bridge",
        "callable":"normalize_strategy_spec",
    },
    "CRW_BACKTEST":{
        "path":"scripts/operator/crw_backtest_summary_13z.py",
        "module":"scripts.operator.crw_backtest_summary_13z",
        "callable":"run_backtest",
    },
    "AUTOTUNER_PARAMETER_CONSUMPTION":{
        "path":"autotuner_parameter_consumption.py",
        "module":"autotuner_parameter_consumption",
        "callable":"parameter_schema_for_tuning",
    },
    "AUTOTUNER_CANDIDATE_GENERATE":{
        "path":"autotuner_strategy_bridge.py",
        "module":"autotuner_strategy_bridge",
        "callable":"candidate_mutations",
    },
    "CANONICAL_DATA_MATERIALIZE":{
        "path":"data_manager.py",
        "module":"data_manager",
        "callable":"DataManager",
    },
}
_SHA1=re.compile(r"^[0-9a-f]{40}$")
_SHA256=re.compile(r"^[0-9a-f]{64}$")
_ID=re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SYMBOL=re.compile(r"^[A-Z0-9._-]{1,24}$")
_IMPORT_LOCK=threading.Lock()

class CanonicalDispatchError(RuntimeError): pass

def cbytes(v:Any)->bytes:
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False,default=str).encode()

def sha(v:Any)->str:return hashlib.sha256(cbytes(v)).hexdigest()

def sha_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

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

def requested_symbols(payload:dict)->list[str]:
    raw=payload.get("symbols")
    if raw is None:raw=payload.get("symbol")
    if isinstance(raw,str):
        values=[x.strip().upper() for x in raw.split(",") if x.strip()]
    elif isinstance(raw,(list,tuple)):
        values=[str(x).strip().upper() for x in raw if str(x).strip()]
    else:
        values=[]
    out=[]
    for symbol in values:
        if not _SYMBOL.fullmatch(symbol):raise CanonicalDispatchError(f"invalid CRW symbol: {symbol!r}")
        if symbol not in out:out.append(symbol)
    if not out or len(out)>32:raise CanonicalDispatchError("CRW_BACKTEST requires 1..32 explicit symbols")
    return out

def resolve_dataset(input_root:Path,symbol:str,node:dict)->dict:
    if not isinstance(node,dict):raise CanonicalDispatchError(f"dataset descriptor must be object: {symbol}")
    exact(node,{"relative_path","sha256","bytes"},"dataset")
    rel=Path(str(node.get("relative_path") or ""))
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        raise CanonicalDispatchError(f"dataset relative_path rejected: {symbol}")
    digest=str(node.get("sha256") or "").lower()
    if not _SHA256.fullmatch(digest):raise CanonicalDispatchError(f"dataset sha256 invalid: {symbol}")
    try:size=int(node.get("bytes"))
    except Exception as e:raise CanonicalDispatchError(f"dataset bytes invalid: {symbol}") from e
    if size<1:raise CanonicalDispatchError(f"dataset bytes must be positive: {symbol}")
    root=input_root.resolve(); path=(root/rel).resolve()
    if root not in path.parents or not path.is_file():raise CanonicalDispatchError(f"governed dataset missing or outside input root: {symbol}")
    actual_size=path.stat().st_size
    if actual_size!=size:raise CanonicalDispatchError(f"dataset byte count mismatch: {symbol}")
    actual_sha=sha_file(path)
    if actual_sha!=digest:raise CanonicalDispatchError(f"dataset sha256 mismatch: {symbol}")
    return {"relative_path":rel.as_posix(),"sha256":actual_sha,"bytes":actual_size,"path":path}

def validate_crw_arguments(args:Any,input_root:Path|None)->dict:
    if not isinstance(args,dict):raise CanonicalDispatchError("CRW_BACKTEST arguments must be object")
    exact(args,{"payload","datasets"},"CRW_BACKTEST arguments")
    payload=args.get("payload")
    datasets=args.get("datasets")
    if not isinstance(payload,dict):raise CanonicalDispatchError("CRW_BACKTEST payload must be object")
    if not isinstance(datasets,dict) or not datasets or len(datasets)>32:
        raise CanonicalDispatchError("CRW_BACKTEST datasets must contain 1..32 symbol descriptors")
    if input_root is None:raise CanonicalDispatchError("CRW_BACKTEST requires governed input_root")
    if "_verified_source_paths" in payload:raise CanonicalDispatchError("caller-supplied _verified_source_paths are forbidden")
    if str(payload.get("strategy_id") or "")!="crw_score_multi_mode":
        raise CanonicalDispatchError("CRW_BACKTEST strategy_id must be crw_score_multi_mode")
    if not str(payload.get("timeframe") or "").strip():raise CanonicalDispatchError("CRW_BACKTEST timeframe is required")
    for key in ("live_allowed","broker_submit","broker_cancel","broker_flatten","place_order","runtime_activation"):
        if payload.get(key) not in (None,False,0,"", "false", "False"):
            raise CanonicalDispatchError(f"CRW_BACKTEST forbids execution authority field: {key}")
    symbols=requested_symbols(payload)
    normalized={}
    for raw_symbol,node in datasets.items():
        symbol=str(raw_symbol or "").strip().upper()
        if not _SYMBOL.fullmatch(symbol):raise CanonicalDispatchError(f"invalid dataset symbol: {raw_symbol!r}")
        resolved=resolve_dataset(input_root,symbol,node)
        normalized[symbol]={k:resolved[k] for k in ("relative_path","sha256","bytes")}
    missing=[s for s in symbols if s not in normalized]
    if missing:raise CanonicalDispatchError(f"CRW_BACKTEST missing governed datasets for symbols={missing}")
    extra=[s for s in normalized if s not in symbols]
    if extra:raise CanonicalDispatchError(f"CRW_BACKTEST contains unrequested datasets for symbols={extra}")
    return {"payload":deepcopy(payload),"datasets":normalized}

def validate_tune_parameters(value:Any)->list[str]:
    if value is None:return []
    if not isinstance(value,list) or len(value)>64 or any(not isinstance(x,str) for x in value):
        raise CanonicalDispatchError("tune_parameters must be a list of at most 64 strings")
    out=[]
    for raw in value:
        key=raw.strip()
        if not key or not _ID.fullmatch(key):raise CanonicalDispatchError(f"invalid tune parameter: {raw!r}")
        if key not in out:out.append(key)
    return out

def validate_autotuner_arguments(cid:str,args:Any)->dict:
    if not isinstance(args,dict):raise CanonicalDispatchError(f"{cid} arguments must be object")
    if cid=="AUTOTUNER_PARAMETER_CONSUMPTION":
        exact(args,{"strategy_spec","tune_parameters"},cid+" arguments")
        max_candidates=None
    else:
        exact(args,{"strategy_spec","tune_parameters","max_candidates"},cid+" arguments")
        try:max_candidates=int(args.get("max_candidates",128))
        except Exception as e:raise CanonicalDispatchError("max_candidates must be integer") from e
        if not 1<=max_candidates<=512:raise CanonicalDispatchError("max_candidates must be within 1..512")
    spec=args.get("strategy_spec")
    if not isinstance(spec,dict):raise CanonicalDispatchError(f"{cid} strategy_spec must be object")
    nested=spec.get("strategy_spec") if isinstance(spec.get("strategy_spec"),dict) else spec
    if str(nested.get("strategy_id") or spec.get("strategy_id") or "")!="crw_score_multi_mode":
        raise CanonicalDispatchError(f"{cid} strategy_id must be crw_score_multi_mode")
    result={"strategy_spec":deepcopy(spec),"tune_parameters":validate_tune_parameters(args.get("tune_parameters"))}
    if max_candidates is not None:result["max_candidates"]=max_candidates
    return result

def validate_data_materialize_arguments(args:Any,input_root:Path|None)->dict:
    if not isinstance(args,dict):raise CanonicalDispatchError("CANONICAL_DATA_MATERIALIZE arguments must be object")
    exact(args,{"asset_type","symbol","source_timeframe","target_timeframes","source_origin","dataset"},"CANONICAL_DATA_MATERIALIZE arguments")
    if str(args.get("asset_type") or "").strip().lower()!="stocks":
        raise CanonicalDispatchError("CANONICAL_DATA_MATERIALIZE v1 currently supports asset_type=stocks")
    symbol=str(args.get("symbol") or "").strip().upper()
    if not _SYMBOL.fullmatch(symbol):raise CanonicalDispatchError("CANONICAL_DATA_MATERIALIZE symbol is invalid")
    source_tf=str(args.get("source_timeframe") or "").strip()
    if not source_tf or len(source_tf)>32 or not re.fullmatch(r"[A-Za-z0-9]+",source_tf):
        raise CanonicalDispatchError("CANONICAL_DATA_MATERIALIZE source_timeframe is invalid")
    targets=args.get("target_timeframes")
    if not isinstance(targets,list) or not targets or len(targets)>16 or any(not isinstance(x,str) for x in targets):
        raise CanonicalDispatchError("CANONICAL_DATA_MATERIALIZE target_timeframes must contain 1..16 strings")
    normalized_targets=[]
    for raw in targets:
        tf=raw.strip()
        if not tf or len(tf)>32 or not re.fullmatch(r"[A-Za-z0-9]+",tf):
            raise CanonicalDispatchError(f"CANONICAL_DATA_MATERIALIZE target timeframe is invalid: {raw!r}")
        if tf not in normalized_targets:normalized_targets.append(tf)
    origin=str(args.get("source_origin") or "").strip()
    if not origin or len(origin)>128 or not re.fullmatch(r"[A-Za-z0-9_.:-]+",origin):
        raise CanonicalDispatchError("CANONICAL_DATA_MATERIALIZE source_origin is invalid")
    if input_root is None:raise CanonicalDispatchError("CANONICAL_DATA_MATERIALIZE requires governed input_root")
    resolved=resolve_dataset(input_root,symbol,args.get("dataset"))
    return {
        "asset_type":"stocks",
        "symbol":symbol,
        "source_timeframe":source_tf,
        "target_timeframes":normalized_targets,
        "source_origin":origin,
        "dataset":{k:resolved[k] for k in ("relative_path","sha256","bytes")},
    }

def validate_request(req:dict,root:Path,source_receipt:dict,input_root:Path|None=None)->dict:
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
    if cid=="STRATEGY_SPEC_VALIDATE":
        if not isinstance(args,dict) or set(args)!={"strategy_spec"} or not isinstance(args.get("strategy_spec"),dict):
            raise CanonicalDispatchError("STRATEGY_SPEC_VALIDATE arguments must contain only strategy_spec object")
        normalized_args=deepcopy(args)
    elif cid=="CRW_BACKTEST":
        normalized_args=validate_crw_arguments(args,input_root)
    elif cid in {"AUTOTUNER_PARAMETER_CONSUMPTION","AUTOTUNER_CANDIDATE_GENERATE"}:
        normalized_args=validate_autotuner_arguments(cid,args)
    elif cid=="CANONICAL_DATA_MATERIALIZE":
        normalized_args=validate_data_materialize_arguments(args,input_root)
    else:
        raise CanonicalDispatchError(f"capability executor is not implemented: {cid}")
    return {"schema":REQUEST_SCHEMA,"job_id":jid,"capability_id":cid,"mmibkr":mm,"entrypoint":{**cap,"git_blob_sha1":actual},"arguments":normalized_args,"resources":resources(req.get("resources")),"authority":AUTHORITY,"forbidden_authorities":dict(FORBIDDEN_AUTHORITY_ASSERTIONS)}

def _inside(root:Path,path:Path)->bool:
    try:path.resolve().relative_to(root.resolve());return True
    except Exception:return False

def load_callable(root:Path,cap:dict):
    want=(root/cap["path"]).resolve(); rp=str(root.resolve()); module_name=cap["module"]
    with _IMPORT_LOCK:
        old=sys.modules.get(module_name)
        if old is not None:
            old_file=Path(str(getattr(old,"__file__","") or ""))
            if not old_file or not _inside(root,old_file):del sys.modules[module_name]
        saved_paths={}
        parts=module_name.split(".")
        for idx in range(1,len(parts)):
            package_name=".".join(parts[:idx]); package=sys.modules.get(package_name)
            private_dir=root.joinpath(*parts[:idx])
            if package is None or not private_dir.is_dir() or not hasattr(package,"__path__"):continue
            current=list(package.__path__); saved_paths[package_name]=current
            package.__path__[:]=[str(private_dir),*[p for p in current if str(p)!=str(private_dir)]]
            child_prefix=package_name+"."
            for name,mod in list(sys.modules.items()):
                if not name.startswith(child_prefix) or name==module_name:continue
                mod_file=Path(str(getattr(mod,"__file__","") or ""))
                if mod_file and not _inside(root,mod_file):del sys.modules[name]
        importlib.invalidate_caches(); added=rp not in sys.path
        if added:sys.path.insert(0,rp)
        try:m=importlib.import_module(module_name)
        finally:
            if added and rp in sys.path:sys.path.remove(rp)
            for package_name,paths in saved_paths.items():
                package=sys.modules.get(package_name)
                if package is not None and hasattr(package,"__path__"):package.__path__[:]=paths
        if Path(str(getattr(m,"__file__","") or "")).resolve()!=want:raise CanonicalDispatchError("imported module path does not match verified entrypoint")
        fn=getattr(m,cap["callable"],None)
        if not callable(fn):raise CanonicalDispatchError("canonical callable missing")
        return fn

def private_callable(root:Path,path:str,module:str,callable_name:str):
    return load_callable(root,{"path":path,"module":module,"callable":callable_name})

def private_blob_identity(root:Path,path:str)->str:
    target=(root/path).resolve()
    if root.resolve() not in target.parents or not target.is_file():raise CanonicalDispatchError(f"canonical dependency missing: {path}")
    return git_blob(target.read_bytes())

def normalized_crw_spec(root:Path,raw:dict)->dict:
    fn=private_callable(root,"autotuner_strategy_bridge.py","autotuner_strategy_bridge","normalize_strategy_spec")
    normalized=fn(raw)
    if not isinstance(normalized,dict) or not isinstance(normalized.get("strategy_spec"),dict):
        raise CanonicalDispatchError("canonical StrategySpec normalizer returned invalid contract")
    digest=str(normalized.get("strategy_spec_digest") or "")
    if not _SHA256.fullmatch(digest):raise CanonicalDispatchError("canonical StrategySpec digest is invalid")
    if normalized["strategy_spec"].get("strategy_id")!="crw_score_multi_mode":
        raise CanonicalDispatchError("AutoTuner capability only accepts crw_score_multi_mode")
    return normalized

def crw_parameter_schema(root:Path)->dict:
    cls=private_callable(root,"strategies/python/crw_score_multi_mode.py","strategies.python.crw_score_multi_mode","CrwScoreMultiModeStrategy")
    schema=cls.parameter_schema()
    if not isinstance(schema,dict) or not schema:raise CanonicalDispatchError("canonical CRW parameter schema is empty")
    return schema

def autotuner_gate(root:Path,args:dict)->tuple[dict,dict,dict]:
    normalized=normalized_crw_spec(root,args["strategy_spec"]); schema=crw_parameter_schema(root)
    gate=private_callable(root,"autotuner_parameter_consumption.py","autotuner_parameter_consumption","parameter_schema_for_tuning")
    filtered,consumption=gate(normalized["strategy_spec"],schema,tune_parameters=args["tune_parameters"])
    if not isinstance(filtered,dict) or not isinstance(consumption,dict):raise CanonicalDispatchError("canonical AutoTuner consumption gate returned invalid contract")
    authority=consumption.get("authority") or {}
    for key,value in {"research_only":True,"automatic_strategy_spec_write":False,"runtime_activation":False,"broker_submit":False}.items():
        if authority.get(key) is not value:raise CanonicalDispatchError(f"AutoTuner consumption authority rejected: {key}")
    return normalized,filtered,consumption

def autotuner_dependencies(root:Path)->dict[str,str]:
    return {
        "autotuner_strategy_bridge.py":private_blob_identity(root,"autotuner_strategy_bridge.py"),
        "autotuner_parameter_consumption.py":private_blob_identity(root,"autotuner_parameter_consumption.py"),
        "strategies/python/crw_score_multi_mode.py":private_blob_identity(root,"strategies/python/crw_score_multi_mode.py"),
    }

def sanitize_crw_result(raw:dict,args:dict)->dict:
    safety=raw.get("safety")
    expected={"broker_submit":False,"cancel":False,"replace":False,"live_unlock":False,"backtest_only":True}
    if not isinstance(safety,dict) or any(safety.get(k) is not v for k,v in expected.items()):
        raise CanonicalDispatchError("canonical CRW backtest safety contract rejected")
    coverage=[]
    input_map=args["datasets"]
    for row in raw.get("data_coverage") or []:
        if not isinstance(row,dict):continue
        symbol=str(row.get("symbol") or "").upper()
        cleaned={k:v for k,v in row.items() if k!="source_path"}
        if symbol in input_map:cleaned["governed_input"]=dict(input_map[symbol])
        coverage.append(cleaned)
    row_sets={
        "trade_rows":raw.get("trade_rows") or [],
        "condition_event_rows":raw.get("condition_event_rows") or [],
        "simulation_trade_rows":raw.get("simulation_trade_rows") or [],
        "simulation_condition_event_rows":raw.get("simulation_condition_event_rows") or [],
        "dca_fill_rows":raw.get("dca_fill_rows") or [],
    }
    result={
        "contract_version":raw.get("contract_version"),
        "ok":raw.get("ok") is True,
        "status":raw.get("status"),
        "strategy_id":raw.get("strategy_id"),
        "symbols":raw.get("symbols") or [],
        "timeframe":raw.get("timeframe"),
        "asset_type":raw.get("asset_type"),
        "parameter_hash":raw.get("parameter_hash"),
        "builder_condition_execution":raw.get("builder_condition_execution"),
        "builder_condition_contract_hash":raw.get("builder_condition_contract_hash"),
        "builder_condition_blockers":raw.get("builder_condition_blockers") or [],
        "total_trades":raw.get("total_trades"),
        "closed_trade_count":raw.get("closed_trade_count"),
        "open_trade_count":raw.get("open_trade_count"),
        "open_trade_mark_to_market":raw.get("open_trade_mark_to_market"),
        "win_rate":raw.get("win_rate"),
        "profit_factor":raw.get("profit_factor"),
        "avg_win":raw.get("avg_win"),
        "avg_loss":raw.get("avg_loss"),
        "gross_pnl":raw.get("gross_pnl"),
        "net_pnl":raw.get("net_pnl"),
        "max_drawdown":raw.get("max_drawdown"),
        "exposure":raw.get("exposure"),
        "symbol_count":raw.get("symbol_count"),
        "trade_row_count":raw.get("trade_row_count"),
        "event_row_count":raw.get("event_row_count"),
        "cost_model":raw.get("cost_model") or {},
        "execution_views":raw.get("execution_views") or {},
        "tv_net_pnl":raw.get("tv_net_pnl"),
        "simulated_net_pnl":raw.get("simulated_net_pnl"),
        "simulated_minus_tv_net_pnl":raw.get("simulated_minus_tv_net_pnl"),
        "data_coverage":coverage,
        "governed_inputs":deepcopy(input_map),
        "raw_result_sha256":sha(raw),
        "row_artifact_sha256":{name:sha(rows) for name,rows in row_sets.items()},
        "row_artifact_counts":{name:len(rows) for name,rows in row_sets.items()},
        "safety":expected,
    }
    return result

def artifact_descriptor(path:Path,artifact_root:Path)->dict:
    root=artifact_root.resolve(); resolved=path.resolve()
    if root not in resolved.parents or not resolved.is_file():
        raise CanonicalDispatchError("materialized artifact missing or outside artifact root")
    return {
        "relative_path":resolved.relative_to(root).as_posix(),
        "sha256":sha_file(resolved),
        "bytes":resolved.stat().st_size,
    }

def materialize_stock_data(v:dict,root:Path,input_root:Path|None,artifact_root:Path|None)->dict:
    if input_root is None:raise CanonicalDispatchError("CANONICAL_DATA_MATERIALIZE requires governed input_root")
    if artifact_root is None:raise CanonicalDispatchError("CANONICAL_DATA_MATERIALIZE requires receipt_dir artifact storage")
    args=v["arguments"]; symbol=args["symbol"]; source_tf=args["source_timeframe"]
    resolved=resolve_dataset(input_root,symbol,args["dataset"])
    try:pd=importlib.import_module("pandas")
    except Exception as e:raise CanonicalDispatchError("CANONICAL_DATA_MATERIALIZE requires pandas runtime dependency") from e
    frame=pd.read_csv(resolved["path"])
    manager_cls=load_callable(root,CAPABILITIES["CANONICAL_DATA_MATERIALIZE"])
    class NoBrokerIB:
        def reqMarketDataType(self,*_args,**_kwargs):return None
    config={
        "DATA_OUTPUT_DIR":str(artifact_root.resolve()),
        "TIMEFRAME":source_tf,
        "TIMEFRAMES":list(args["target_timeframes"]),
        "SR_ENABLED":False,
        "HISTORICAL_DEDICATED_CLIENT":False,
        "WRITE_AGGREGATE":1,
        "SAVE_FEATURES_CSV":1,
        "INCREMENTAL_FETCH":0,
        "USE_RTH":0,
    }
    manager=manager_cls(config,NoBrokerIB())
    raw=manager.ingest_external_stock_source_bars(
        symbol,
        source_tf,
        frame,
        target_timeframes=list(args["target_timeframes"]),
        source_origin=args["source_origin"],
    )
    if not isinstance(raw,dict) or raw.get("ok") is not True or raw.get("broker_request_made") is not False:
        raise CanonicalDispatchError("canonical DataManager external-source ingest safety contract rejected")
    frames=raw.get("frames")
    if not isinstance(frames,dict) or not frames:raise CanonicalDispatchError("canonical DataManager returned no materialized frames")
    outputs=[]; artifacts=[]
    for tf,node in frames.items():
        if node is None or not hasattr(node,"__len__"):raise CanonicalDispatchError("canonical DataManager frame contract is invalid")
        raw_path=manager._path_for("stocks",symbol,str(tf),features=False)
        features_path=manager._path_for("stocks",symbol,str(tf),features=True)
        sidecar=features_path.with_suffix(features_path.suffix+".manifest.json")
        raw_desc=artifact_descriptor(raw_path,artifact_root)
        feature_desc=artifact_descriptor(features_path,artifact_root)
        sidecar_desc=artifact_descriptor(sidecar,artifact_root)
        artifacts.extend([raw_desc,feature_desc,sidecar_desc])
        first=None;last=None
        try:
            if len(node) and "timestamp" in node.columns:
                first=str(node["timestamp"].iloc[0]);last=str(node["timestamp"].iloc[-1])
        except Exception:pass
        try:sidecar_payload=load(sidecar)
        except Exception as e:raise CanonicalDispatchError("feature artifact sidecar is invalid") from e
        manifest_hash=str(sidecar_payload.get("feature_manifest_hash") or "")
        if not _SHA256.fullmatch(manifest_hash):raise CanonicalDispatchError("feature artifact sidecar manifest hash is invalid")
        outputs.append({
            "timeframe":str(tf),
            "rows":int(len(node)),
            "first_timestamp":first,
            "latest_timestamp":last,
            "raw_artifact":raw_desc,
            "feature_artifact":feature_desc,
            "feature_sidecar":sidecar_desc,
            "feature_manifest_hash":manifest_hash,
        })
    aggregate_path=manager._aggregate_path("stocks",symbol)
    aggregate=None
    if aggregate_path.is_file():
        aggregate=artifact_descriptor(aggregate_path,artifact_root);artifacts.append(aggregate)
    return {
        "schema":"mmibkr.canonical_data_materialization.v1",
        "asset_type":"stocks",
        "symbol":symbol,
        "source_timeframe":source_tf,
        "target_timeframes":[str(x) for x in frames],
        "source_origin":args["source_origin"],
        "source_dataset":dict(args["dataset"]),
        "frame_count":len(outputs),
        "frames":outputs,
        "aggregate_artifact":aggregate,
        "artifact_count":len(artifacts),
        "artifacts":artifacts,
        "broker_request_made":False,
        "canonical_dependencies":{
            "data_manager.py":private_blob_identity(root,"data_manager.py"),
            "feature_contract.py":private_blob_identity(root,"feature_contract.py"),
        },
        "safety":{
            "market_data_acquisition":False,
            "historical_data_requests":False,
            "broker_submit":False,
            "broker_cancel":False,
            "broker_flatten":False,
            "runtime_activation":False,
            "live_trading":False,
        },
    }

def execute_valid(v:dict,root:Path,input_root:Path|None=None,artifact_root:Path|None=None)->dict:
    fn=None if v["capability_id"]=="CANONICAL_DATA_MATERIALIZE" else load_callable(root,CAPABILITIES[v["capability_id"]])
    if v["capability_id"]=="STRATEGY_SPEC_VALIDATE":
        raw=fn(v["arguments"]["strategy_spec"])
        if not isinstance(raw,dict) or not isinstance(raw.get("strategy_spec"),dict) or not _SHA256.fullmatch(str(raw.get("strategy_spec_digest") or "")):
            raise CanonicalDispatchError("canonical StrategySpec validator returned invalid contract")
        result={"strategy_spec":raw["strategy_spec"],"strategy_spec_digest":raw["strategy_spec_digest"]}
    elif v["capability_id"]=="CRW_BACKTEST":
        if input_root is None:raise CanonicalDispatchError("CRW_BACKTEST requires governed input_root")
        verified={}
        for symbol,node in v["arguments"]["datasets"].items():
            resolved=resolve_dataset(input_root,symbol,node);verified[symbol]=str(resolved["path"])
        payload=deepcopy(v["arguments"]["payload"]);payload["_verified_source_paths"]=verified
        raw=fn(payload,input_root.resolve())
        if not isinstance(raw,dict):raise CanonicalDispatchError("canonical CRW backtest returned invalid contract")
        result=sanitize_crw_result(raw,v["arguments"])
    elif v["capability_id"]=="AUTOTUNER_PARAMETER_CONSUMPTION":
        normalized,filtered,consumption=autotuner_gate(root,v["arguments"])
        result={
            "strategy_spec_digest":normalized["strategy_spec_digest"],
            "searchable_parameter_schema":filtered,
            "consumption":consumption,
            "canonical_dependencies":autotuner_dependencies(root),
        }
    elif v["capability_id"]=="AUTOTUNER_CANDIDATE_GENERATE":
        normalized,filtered,consumption=autotuner_gate(root,v["arguments"])
        candidates=fn(normalized["strategy_spec"],filtered,tune_parameters=v["arguments"]["tune_parameters"],max_candidates=v["arguments"]["max_candidates"])
        if not isinstance(candidates,list) or len(candidates)>v["arguments"]["max_candidates"]:
            raise CanonicalDispatchError("canonical candidate generator returned invalid candidate set")
        result={
            "strategy_spec_digest":normalized["strategy_spec_digest"],
            "candidate_count":len(candidates),
            "candidates":candidates,
            "candidate_set_sha256":sha(candidates),
            "searchable_parameters":list(filtered),
            "consumption":consumption,
            "canonical_dependencies":autotuner_dependencies(root),
        }
    elif v["capability_id"]=="CANONICAL_DATA_MATERIALIZE":
        result=materialize_stock_data(v,root,input_root,artifact_root)
    else:
        raise CanonicalDispatchError(f"capability executor is not implemented: {v['capability_id']}")
    rb=cbytes(result)
    if len(rb)>v["resources"]["max_output_bytes"]:raise CanonicalDispatchError("canonical result exceeded max_output_bytes")
    fp=sha(v)
    return {"schema":RECEIPT_SCHEMA,"job_id":v["job_id"],"job_fingerprint":fp,"capability_id":v["capability_id"],"status":"completed","authority":{"research_only":True,**FORBIDDEN_AUTHORITY_ASSERTIONS},"mmibkr":v["mmibkr"],"entrypoint":v["entrypoint"],"resources":v["resources"],"result_sha256":hashlib.sha256(rb).hexdigest(),"result":result}

def safe_execute_valid(v:dict,root:Path,input_root:Path|None=None,artifact_root:Path|None=None)->dict:
    try:
        return execute_valid(v,root,input_root=input_root,artifact_root=artifact_root)
    except CanonicalDispatchError:
        raise
    except Exception as e:
        raise CanonicalDispatchError(
            f"canonical {v.get('capability_id') or 'workload'} execution failed: {type(e).__name__}"
        ) from e

def atomic(path:Path,v:dict):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"); tmp.write_bytes(cbytes(v)+b"\n"); os.replace(tmp,path)

def cached(path:Path,fp:str):
    if not path.is_file():return None
    r=load(path)
    if r.get("schema")!=RECEIPT_SCHEMA or r.get("job_fingerprint")!=fp or r.get("status")!="completed":raise CanonicalDispatchError("cached receipt identity/status mismatch")
    return r

def validate_materialization_cache(receipt:dict,receipt_dir:Path,fp:str)->None:
    if receipt.get("capability_id")!="CANONICAL_DATA_MATERIALIZE":return
    result=receipt.get("result") or {}; artifacts=result.get("artifacts")
    if not isinstance(artifacts,list) or not artifacts:
        raise CanonicalDispatchError("cached materialization receipt has no artifacts")
    root=(receipt_dir/"artifacts"/fp).resolve()
    for node in artifacts:
        if not isinstance(node,dict):raise CanonicalDispatchError("cached materialization artifact descriptor invalid")
        rel=Path(str(node.get("relative_path") or ""))
        if rel.is_absolute() or not rel.parts or ".." in rel.parts:
            raise CanonicalDispatchError("cached materialization artifact path invalid")
        path=(root/rel).resolve()
        if root not in path.parents or not path.is_file():
            raise CanonicalDispatchError("cached materialization artifact missing")
        if path.stat().st_size!=int(node.get("bytes") or -1) or sha_file(path)!=str(node.get("sha256") or ""):
            raise CanonicalDispatchError("cached materialization artifact hash mismatch")

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

def execute_request(req:dict,*,source_root:Path,source_receipt:dict,input_root:Path|None=None,receipt_dir:Path|None=None)->dict:
    v=validate_request(req,source_root,source_receipt,input_root=input_root); fp=sha(v)
    if receipt_dir is None:
        if v["capability_id"]=="CANONICAL_DATA_MATERIALIZE":
            raise CanonicalDispatchError("CANONICAL_DATA_MATERIALIZE requires receipt_dir artifact storage")
        return {"receipt":safe_execute_valid(v,source_root,input_root=input_root),"cache_hit":False}
    rd=receipt_dir.resolve(); rp=rd/"receipts"/f"{fp}.json"; hit=cached(rp,fp)
    if hit:
        validate_materialization_cache(hit,rd,fp)
        return {"receipt":hit,"cache_hit":True}
    cp=rd/"claims"/f"{fp}.claim"
    token,hit=acquire_claim(cp,v,fp,rp)
    if hit:
        validate_materialization_cache(hit,rd,fp)
        return {"receipt":hit,"cache_hit":True}
    stop,lost,thread=start_claim_heartbeat(cp,token,fp)
    published=False
    artifact_root=(rd/"artifacts"/fp).resolve() if v["capability_id"]=="CANONICAL_DATA_MATERIALIZE" else None
    if artifact_root is not None:
        shutil.rmtree(artifact_root,ignore_errors=True);artifact_root.mkdir(parents=True,exist_ok=True)
    try:
        r=safe_execute_valid(v,source_root,input_root=input_root,artifact_root=artifact_root)
        if lost.is_set() or not claim_owned(cp,token,fp):
            raise CanonicalDispatchError("claim lease ownership was lost; canonical result discarded")
        atomic(rp,r);published=True;return {"receipt":r,"cache_hit":False}
    except Exception:
        if artifact_root is not None and not published:shutil.rmtree(artifact_root,ignore_errors=True)
        raise
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

def execute_plan(plan:dict,*,source_root:Path,source_receipt:dict,receipt_dir:Path,input_root:Path|None=None)->dict:
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
                x=execute_request(pending[j]["request"],source_root=source_root,source_receipt=source_receipt,input_root=input_root,receipt_dir=receipt_dir);r=x["receipt"]
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
        q=sub.add_parser(name);q.add_argument("--source-root",required=True);q.add_argument("--source-receipt",required=True);q.add_argument("--input-root");q.add_argument("--receipt-dir",required=name=="plan-run");q.add_argument("--request" if name=="run" else "--plan",required=True)
    a=ap.parse_args();root=Path(a.source_root).resolve();sr=load(Path(a.source_receipt));ir=Path(a.input_root).resolve() if a.input_root else None;rd=Path(a.receipt_dir).resolve() if a.receipt_dir else None
    try:
        out=execute_request(load(Path(a.request)),source_root=root,source_receipt=sr,input_root=ir,receipt_dir=rd) if a.cmd=="run" else execute_plan(load(Path(a.plan)),source_root=root,source_receipt=sr,input_root=ir,receipt_dir=rd)
        print(json.dumps(out,sort_keys=True));return 0
    except CanonicalDispatchError as e:print(json.dumps({"ok":False,"error":str(e)},sort_keys=True),file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())
