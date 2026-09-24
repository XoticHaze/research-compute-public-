from __future__ import annotations
"""Portable fail-closed dispatcher for allowlisted MM-IBKR research work."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import csv
import hashlib, importlib, json, os, re, secrets, shutil, sys, tempfile, threading, time
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
    "FEATURE_CONTRACT_VALIDATE":{
        "path":"feature_contract.py",
        "module":"feature_contract",
        "callable":"read_feature_artifact_sidecar",
    },
    "STRATEGY_PREVIEW":{
        "path":"strategies/__init__.py",
        "module":"strategies",
        "callable":"create",
    },
    "AUTOTUNER_CAMPAIGN":{
        "path":"autotuner_campaign_runner.py",
        "module":"autotuner_campaign_runner",
        "callable":"run_campaign_iteration",
    },
    "AUTOTUNER_PRIMARY_VALIDATION":{
        "path":"autotuner_primary_validation_runner.py",
        "module":"autotuner_primary_validation_runner",
        "callable":"execute_primary_validation",
    },
    "MODEL_LAB_FIRST_CONSUMER":{
        "path":"scripts/operator/model_lab_xgboost_first_consumer.py",
        "module":"scripts.operator.model_lab_xgboost_first_consumer",
        "callable":"execute",
    },
    "MODEL_LAB_COMPARE_VALIDATE":{
        "path":"model_lab_comparison_matrix.py",
        "module":"model_lab_comparison_matrix",
        "callable":"align_training_matrices_for_comparison",
    },
    "NEWS_REPLAY_ANALYZE":{
        "path":"news_engine.py",
        "module":"news_engine",
        "callable":"NewsEngine",
    },
    "OPTIONS_SNAPSHOT_ANALYZE":{
        "path":"options_scanner.py",
        "module":"options_scanner",
        "callable":"OptionsScanner",
    },
    "NEWS_FEATURE_SIDECAR_BUILD":{
        "path":"scripts/operator/news_feature_sidecar_probe_14ni.py",
        "module":"scripts.operator.news_feature_sidecar_probe_14ni",
        "callable":"_score_row",
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

def _crw_strategy_spec_from_args(args:dict,cid:str)->dict:
    spec=args.get("strategy_spec")
    if not isinstance(spec,dict):raise CanonicalDispatchError(f"{cid} strategy_spec must be object")
    nested=spec.get("strategy_spec") if isinstance(spec.get("strategy_spec"),dict) else spec
    if str(nested.get("strategy_id") or spec.get("strategy_id") or "")!="crw_score_multi_mode":
        raise CanonicalDispatchError(f"{cid} strategy_id must be crw_score_multi_mode")
    symbol=str(nested.get("symbol") or spec.get("symbol") or "").strip().upper()
    timeframe=str(nested.get("timeframe") or spec.get("timeframe") or "").strip()
    if not _SYMBOL.fullmatch(symbol):raise CanonicalDispatchError(f"{cid} symbol is invalid")
    if not timeframe or len(timeframe)>32:raise CanonicalDispatchError(f"{cid} timeframe is invalid")
    return deepcopy(spec)

def _validated_tuner_dataset(args:dict,cid:str,input_root:Path|None)->dict:
    if input_root is None:raise CanonicalDispatchError(f"{cid} requires governed input_root")
    node=args.get("dataset")
    return {k:v for k,v in resolve_dataset(input_root,"autotuner",node).items() if k in {"relative_path","sha256","bytes"}}

def validate_autotuner_campaign_arguments(args:Any,input_root:Path|None)->dict:
    cid="AUTOTUNER_CAMPAIGN"
    if not isinstance(args,dict):raise CanonicalDispatchError(f"{cid} arguments must be object")
    exact(args,{"strategy_spec","dataset","tune_parameters","advisory_suggestions","batch_size","coarse_points","score_tolerance_fraction","state","history"},cid+" arguments")
    spec=_crw_strategy_spec_from_args(args,cid)
    dataset=_validated_tuner_dataset(args,cid,input_root)
    tune=validate_tune_parameters(args.get("tune_parameters"))
    try:
        batch=int(args.get("batch_size",12)); coarse=int(args.get("coarse_points",5)); tolerance=float(args.get("score_tolerance_fraction",0.05))
    except Exception as e:raise CanonicalDispatchError(f"{cid} numeric bounds are invalid") from e
    if not 1<=batch<=32:raise CanonicalDispatchError(f"{cid} batch_size must be within 1..32")
    if not 2<=coarse<=11:raise CanonicalDispatchError(f"{cid} coarse_points must be within 2..11")
    if not 0.0<=tolerance<=0.5:raise CanonicalDispatchError(f"{cid} score_tolerance_fraction must be within 0..0.5")
    advisory=args.get("advisory_suggestions") or []
    if not isinstance(advisory,list) or len(advisory)>32:raise CanonicalDispatchError(f"{cid} advisory_suggestions must be list <=32")
    normalized_advisory=[]
    for idx,row in enumerate(advisory):
        if not isinstance(row,dict):raise CanonicalDispatchError(f"{cid} advisory_suggestions[{idx}] must be object")
        exact(row,{"parameter","values","hypothesis","rationale"},f"{cid} advisory_suggestions[{idx}]")
        parameter=str(row.get("parameter") or "").strip()
        values=row.get("values")
        if not _ID.fullmatch(parameter) or not isinstance(values,list) or not values or len(values)>16:
            raise CanonicalDispatchError(f"{cid} advisory_suggestions[{idx}] is invalid")
        hypothesis=str(row.get("hypothesis") or "")
        rationale=str(row.get("rationale") or "")
        if len(hypothesis)>1000 or len(rationale)>1000:raise CanonicalDispatchError(f"{cid} advisory text is too long")
        normalized_advisory.append({"parameter":parameter,"values":deepcopy(values),"hypothesis":hypothesis,"rationale":rationale})
    state=args.get("state"); history=args.get("history")
    if state is not None and not isinstance(state,dict):raise CanonicalDispatchError(f"{cid} state must be object or null")
    if history is not None and not isinstance(history,dict):raise CanonicalDispatchError(f"{cid} history must be object or null")
    return {
        "strategy_spec":spec,"dataset":dataset,"tune_parameters":tune,
        "advisory_suggestions":normalized_advisory,"batch_size":batch,"coarse_points":coarse,
        "score_tolerance_fraction":tolerance,"state":deepcopy(state),"history":deepcopy(history),
    }

def validate_autotuner_primary_validation_arguments(args:Any,input_root:Path|None)->dict:
    cid="AUTOTUNER_PRIMARY_VALIDATION"
    if not isinstance(args,dict):raise CanonicalDispatchError(f"{cid} arguments must be object")
    exact(args,{"strategy_spec","dataset","staged_plan","split_policy"},cid+" arguments")
    spec=_crw_strategy_spec_from_args(args,cid)
    dataset=_validated_tuner_dataset(args,cid,input_root)
    plan=args.get("staged_plan")
    if not isinstance(plan,dict):raise CanonicalDispatchError(f"{cid} staged_plan must be object")
    data_ref=plan.get("canonical_data_ref")
    if not isinstance(data_ref,dict) or str(data_ref.get("dataset_sha256") or "").lower()!=dataset["sha256"]:
        raise CanonicalDispatchError(f"{cid} staged_plan dataset identity mismatch")
    for key in ("automatic_promotion","automatic_strategy_spec_write","runtime_activation","broker_submit"):
        if plan.get(key) not in (None,False):raise CanonicalDispatchError(f"{cid} staged_plan authority rejected: {key}")
    policy=args.get("split_policy")
    if not isinstance(policy,dict):raise CanonicalDispatchError(f"{cid} split_policy must be object")
    exact(policy,{"start_year","test_span_years","embargo_bars","purge_bars","min_test_rows","warmup_bars"},cid+" split_policy")
    normalized_policy={}
    bounds={
        "start_year":(1900,2200),"test_span_years":(1,20),"embargo_bars":(0,100000),
        "purge_bars":(0,100000),"min_test_rows":(1,10000000),"warmup_bars":(0,1000000),
    }
    for key,(low,high) in bounds.items():
        try:value=int(policy.get(key))
        except Exception as e:raise CanonicalDispatchError(f"{cid} split_policy {key} must be integer") from e
        if not low<=value<=high:raise CanonicalDispatchError(f"{cid} split_policy {key} outside bounds")
        normalized_policy[key]=value
    return {"strategy_spec":spec,"dataset":dataset,"staged_plan":deepcopy(plan),"split_policy":normalized_policy}

def resolve_artifact_ref(input_root:Path|None,receipt_dir:Path|None,node:Any,label:str)->dict:
    if not isinstance(node,dict):raise CanonicalDispatchError(f"{label} must be object")
    scope=str(node.get("scope") or "").strip()
    if scope=="input_root":
        exact(node,{"scope","relative_path","sha256","bytes"},label)
        if input_root is None:raise CanonicalDispatchError(f"{label} input_root scope requires governed input_root")
        root=input_root.resolve()
        job_fingerprint=None
    elif scope=="receipt_artifact":
        exact(node,{"scope","job_fingerprint","relative_path","sha256","bytes"},label)
        if receipt_dir is None:raise CanonicalDispatchError(f"{label} receipt_artifact scope requires receipt_dir")
        job_fingerprint=str(node.get("job_fingerprint") or "").lower()
        if not _SHA256.fullmatch(job_fingerprint):raise CanonicalDispatchError(f"{label} job_fingerprint is invalid")
        root=(receipt_dir.resolve()/"artifacts"/job_fingerprint).resolve()
    else:
        raise CanonicalDispatchError(f"{label} scope must be input_root or receipt_artifact")
    rel=Path(str(node.get("relative_path") or ""))
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:raise CanonicalDispatchError(f"{label} relative_path rejected")
    digest=str(node.get("sha256") or "").lower()
    if not _SHA256.fullmatch(digest):raise CanonicalDispatchError(f"{label} sha256 invalid")
    try:size=int(node.get("bytes"))
    except Exception as e:raise CanonicalDispatchError(f"{label} bytes invalid") from e
    if size<1:raise CanonicalDispatchError(f"{label} bytes must be positive")
    path=(root/rel).resolve()
    if root not in path.parents or not path.is_file():raise CanonicalDispatchError(f"{label} missing or outside governed root")
    if path.stat().st_size!=size:raise CanonicalDispatchError(f"{label} byte count mismatch")
    actual=sha_file(path)
    if actual!=digest:raise CanonicalDispatchError(f"{label} sha256 mismatch")
    out={"scope":scope,"relative_path":rel.as_posix(),"sha256":actual,"bytes":size,"path":path}
    if job_fingerprint is not None:out["job_fingerprint"]=job_fingerprint
    return out

def validate_feature_contract_arguments(args:Any,input_root:Path|None,receipt_dir:Path|None)->dict:
    if not isinstance(args,dict):raise CanonicalDispatchError("FEATURE_CONTRACT_VALIDATE arguments must be object")
    exact(args,{"feature_artifact","expected_manifest_hash","expected_semantic_hash"},"FEATURE_CONTRACT_VALIDATE arguments")
    resolved=resolve_artifact_ref(input_root,receipt_dir,args.get("feature_artifact"),"feature_artifact")
    expected_manifest=str(args.get("expected_manifest_hash") or "").lower()
    expected_semantic=str(args.get("expected_semantic_hash") or "").lower()
    if expected_manifest and not _SHA256.fullmatch(expected_manifest):
        raise CanonicalDispatchError("FEATURE_CONTRACT_VALIDATE expected_manifest_hash is invalid")
    if expected_semantic and not _SHA256.fullmatch(expected_semantic):
        raise CanonicalDispatchError("FEATURE_CONTRACT_VALIDATE expected_semantic_hash is invalid")
    ref={k:resolved[k] for k in ("scope","relative_path","sha256","bytes")}
    if "job_fingerprint" in resolved:ref["job_fingerprint"]=resolved["job_fingerprint"]
    return {
        "feature_artifact":ref,
        "expected_manifest_hash":expected_manifest or None,
        "expected_semantic_hash":expected_semantic or None,
    }

def validate_strategy_preview_arguments(args:Any,input_root:Path|None,receipt_dir:Path|None)->dict:
    if not isinstance(args,dict):raise CanonicalDispatchError("STRATEGY_PREVIEW arguments must be object")
    exact(args,{"strategy_spec","feature_artifact","row_policy","lookback_rows","context_values","expected_feature_semantic_hash"},"STRATEGY_PREVIEW arguments")
    spec=args.get("strategy_spec")
    if not isinstance(spec,dict):raise CanonicalDispatchError("STRATEGY_PREVIEW strategy_spec must be object")
    resolved=resolve_artifact_ref(input_root,receipt_dir,args.get("feature_artifact"),"feature_artifact")
    row_policy=str(args.get("row_policy") or "latest").strip()
    if row_policy not in {"latest","latest_execution_safe"}:
        raise CanonicalDispatchError("STRATEGY_PREVIEW row_policy must be latest or latest_execution_safe")
    try:lookback=int(args.get("lookback_rows",12))
    except Exception as e:raise CanonicalDispatchError("STRATEGY_PREVIEW lookback_rows must be integer") from e
    if not 1<=lookback<=100:raise CanonicalDispatchError("STRATEGY_PREVIEW lookback_rows must be within 1..100")
    context=args.get("context_values")
    if context is None:context={}
    if not isinstance(context,dict):raise CanonicalDispatchError("STRATEGY_PREVIEW context_values must be object")
    semantic=str(args.get("expected_feature_semantic_hash") or "").lower()
    if semantic and not _SHA256.fullmatch(semantic):
        raise CanonicalDispatchError("STRATEGY_PREVIEW expected_feature_semantic_hash is invalid")
    ref={k:resolved[k] for k in ("scope","relative_path","sha256","bytes")}
    if "job_fingerprint" in resolved:ref["job_fingerprint"]=resolved["job_fingerprint"]
    return {
        "strategy_spec":deepcopy(spec),
        "feature_artifact":ref,
        "row_policy":row_policy,
        "lookback_rows":lookback,
        "context_values":deepcopy(context),
        "expected_feature_semantic_hash":semantic or None,
    }

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

def validate_model_lab_first_consumer_arguments(args:Any,input_root:Path|None)->dict:
    cid="MODEL_LAB_FIRST_CONSUMER"
    if not isinstance(args,dict):raise CanonicalDispatchError(f"{cid} arguments must be object")
    exact(args,{"asset_type","symbol","timeframe","horizon_bars","target_name","start_year","test_span_years","min_test_rows","inputs"},cid+" arguments")
    asset_type=str(args.get("asset_type") or "").strip().lower()
    if asset_type not in {"stocks","futures"}:raise CanonicalDispatchError(f"{cid} asset_type must be stocks or futures")
    symbol=str(args.get("symbol") or "").strip().upper()
    identity_symbol=symbol
    if asset_type=="futures" and identity_symbol.endswith("1!"):identity_symbol=identity_symbol[:-2]
    if asset_type=="futures" and identity_symbol.endswith("-CONTINUOUS"):identity_symbol=identity_symbol[:-11]
    if not identity_symbol or not _SYMBOL.fullmatch(identity_symbol):raise CanonicalDispatchError(f"{cid} symbol is invalid")
    timeframe=str(args.get("timeframe") or "").strip()
    if not timeframe or len(timeframe)>32 or not re.fullmatch(r"[A-Za-z0-9]+",timeframe):
        raise CanonicalDispatchError(f"{cid} timeframe is invalid")
    target_name=str(args.get("target_name") or "").strip()
    if not _ID.fullmatch(target_name):raise CanonicalDispatchError(f"{cid} target_name is invalid")
    try:
        horizon=int(args.get("horizon_bars")); start_year=int(args.get("start_year"))
        test_span=int(args.get("test_span_years")); min_rows=int(args.get("min_test_rows"))
    except Exception as e:raise CanonicalDispatchError(f"{cid} numeric bounds must be integers") from e
    if not 1<=horizon<=1000:raise CanonicalDispatchError(f"{cid} horizon_bars must be within 1..1000")
    if not 1900<=start_year<=2200:raise CanonicalDispatchError(f"{cid} start_year must be within 1900..2200")
    if not 1<=test_span<=20:raise CanonicalDispatchError(f"{cid} test_span_years must be within 1..20")
    if not 1<=min_rows<=10_000_000:raise CanonicalDispatchError(f"{cid} min_test_rows must be within 1..10000000")
    if input_root is None:raise CanonicalDispatchError(f"{cid} requires governed input_root")
    inputs=args.get("inputs")
    if not isinstance(inputs,dict):raise CanonicalDispatchError(f"{cid} inputs must be object")
    exact(inputs,{"raw","features","feature_sidecar"},cid+" inputs")
    resolved={}
    for name in ("raw","features","feature_sidecar"):
        node=resolve_dataset(input_root,f"model_lab_{name}",inputs[name])
        resolved[name]={k:node[k] for k in ("relative_path","sha256","bytes")}
    return {
        "asset_type":asset_type,"symbol":symbol,"timeframe":timeframe,
        "horizon_bars":horizon,"target_name":target_name,"start_year":start_year,
        "test_span_years":test_span,"min_test_rows":min_rows,"inputs":resolved,
    }


def validate_model_lab_compare_validate_arguments(args:Any,input_root:Path|None)->dict:
    cid="MODEL_LAB_COMPARE_VALIDATE"
    if not isinstance(args,dict):raise CanonicalDispatchError(f"{cid} arguments must be object")
    exact(args,{"target_name","target_identity","min_shared_rows","horizon_bars","start_year","test_span_years","embargo_bars","purge_bars","min_test_rows","inputs"},cid+" arguments")
    target_name=str(args.get("target_name") or "").strip()
    target_identity=str(args.get("target_identity") or "").strip()
    if not _ID.fullmatch(target_name):raise CanonicalDispatchError(f"{cid} target_name is invalid")
    if not _ID.fullmatch(target_identity):raise CanonicalDispatchError(f"{cid} target_identity is invalid")
    try:
        min_shared=int(args.get("min_shared_rows")); horizon=int(args.get("horizon_bars"))
        start_year=int(args.get("start_year")); test_span=int(args.get("test_span_years"))
        embargo=int(args.get("embargo_bars")); purge=int(args.get("purge_bars"))
        min_test=int(args.get("min_test_rows"))
    except Exception as e:raise CanonicalDispatchError(f"{cid} numeric bounds must be integers") from e
    if not 1<=min_shared<=10_000_000:raise CanonicalDispatchError(f"{cid} min_shared_rows must be within 1..10000000")
    if not 1<=horizon<=1000:raise CanonicalDispatchError(f"{cid} horizon_bars must be within 1..1000")
    if not 1900<=start_year<=2200:raise CanonicalDispatchError(f"{cid} start_year must be within 1900..2200")
    if not 1<=test_span<=20:raise CanonicalDispatchError(f"{cid} test_span_years must be within 1..20")
    if not 0<=embargo<=100_000 or not 0<=purge<=100_000:raise CanonicalDispatchError(f"{cid} embargo_bars/purge_bars must be within 0..100000")
    if not 1<=min_test<=10_000_000:raise CanonicalDispatchError(f"{cid} min_test_rows must be within 1..10000000")
    if embargo<horizon or purge<horizon:raise CanonicalDispatchError(f"{cid} embargo_bars and purge_bars must each cover horizon_bars")
    if input_root is None:raise CanonicalDispatchError(f"{cid} requires governed input_root")
    inputs=args.get("inputs")
    if not isinstance(inputs,dict):raise CanonicalDispatchError(f"{cid} inputs must be object")
    exact(inputs,{"incumbent_matrix","challenger_matrix"},cid+" inputs")
    resolved={}
    for name in ("incumbent_matrix","challenger_matrix"):
        node=resolve_dataset(input_root,f"model_lab_{name}",inputs[name])
        resolved[name]={k:node[k] for k in ("relative_path","sha256","bytes")}
    return {
        "target_name":target_name,"target_identity":target_identity,"min_shared_rows":min_shared,
        "horizon_bars":horizon,"start_year":start_year,"test_span_years":test_span,
        "embargo_bars":embargo,"purge_bars":purge,"min_test_rows":min_test,"inputs":resolved,
    }


def _news_symbols(value:Any,label:str="symbols")->list[str]:
    if not isinstance(value,list) or not value or len(value)>256:
        raise CanonicalDispatchError(f"NEWS_REPLAY_ANALYZE {label} must contain 1..256 symbols")
    out=[]
    for raw in value:
        symbol=str(raw or "").strip().upper()
        if not _SYMBOL.fullmatch(symbol):
            raise CanonicalDispatchError(f"NEWS_REPLAY_ANALYZE invalid symbol: {raw!r}")
        if symbol not in out:out.append(symbol)
    return out

def _news_aliases(value:Any,symbols:list[str])->dict[str,list[str]]:
    if value is None:return {}
    if not isinstance(value,dict) or len(value)>256:
        raise CanonicalDispatchError("NEWS_REPLAY_ANALYZE symbol_aliases must be an object with at most 256 symbols")
    allowed=set(symbols);out={}
    for raw_symbol,raw_values in value.items():
        symbol=str(raw_symbol or "").strip().upper()
        if symbol not in allowed:
            raise CanonicalDispatchError(f"NEWS_REPLAY_ANALYZE alias symbol is outside universe: {symbol}")
        if not isinstance(raw_values,list) or len(raw_values)>32:
            raise CanonicalDispatchError(f"NEWS_REPLAY_ANALYZE aliases for {symbol} must contain at most 32 strings")
        vals=[]
        for raw in raw_values:
            alias=str(raw or "").strip()
            if not 3<=len(alias)<=128:
                raise CanonicalDispatchError(f"NEWS_REPLAY_ANALYZE alias length invalid for {symbol}")
            if alias not in vals:vals.append(alias)
        if vals:out[symbol]=vals
    return out

def _news_theme_map(value:Any,symbols:list[str])->dict[str,list[str]]:
    if value is None:return {}
    if not isinstance(value,dict) or len(value)>64:
        raise CanonicalDispatchError("NEWS_REPLAY_ANALYZE theme_ticker_map must be an object with at most 64 themes")
    allowed=set(symbols);out={}
    for raw_theme,raw_symbols in value.items():
        theme=str(raw_theme or "").strip()
        if not 1<=len(theme)<=64:
            raise CanonicalDispatchError("NEWS_REPLAY_ANALYZE theme name is invalid")
        if not isinstance(raw_symbols,list) or len(raw_symbols)>64:
            raise CanonicalDispatchError(f"NEWS_REPLAY_ANALYZE theme {theme!r} symbols must contain at most 64 values")
        vals=[]
        for raw in raw_symbols:
            symbol=str(raw or "").strip().upper()
            if symbol not in allowed:
                raise CanonicalDispatchError(f"NEWS_REPLAY_ANALYZE theme symbol is outside universe: {symbol}")
            if symbol not in vals:vals.append(symbol)
        if vals:out[theme]=vals
    return out

def validate_news_replay_arguments(args:Any,input_root:Path|None)->dict:
    if not isinstance(args,dict):
        raise CanonicalDispatchError("NEWS_REPLAY_ANALYZE arguments must be object")
    exact(args,{"dataset","symbols","symbol_aliases","theme_ticker_map","max_items"},"NEWS_REPLAY_ANALYZE arguments")
    if input_root is None:
        raise CanonicalDispatchError("NEWS_REPLAY_ANALYZE requires governed input_root")
    symbols=_news_symbols(args.get("symbols"))
    aliases=_news_aliases(args.get("symbol_aliases"),symbols)
    themes=_news_theme_map(args.get("theme_ticker_map"),symbols)
    try:max_items=int(args.get("max_items",800))
    except Exception as e:raise CanonicalDispatchError("NEWS_REPLAY_ANALYZE max_items must be integer") from e
    if not 1<=max_items<=5000:
        raise CanonicalDispatchError("NEWS_REPLAY_ANALYZE max_items must be within 1..5000")
    resolved=resolve_dataset(input_root,"news_replay",args.get("dataset"))
    return {
        "dataset":{k:resolved[k] for k in ("relative_path","sha256","bytes")},
        "symbols":symbols,
        "symbol_aliases":aliases,
        "theme_ticker_map":themes,
        "max_items":max_items,
    }


_OPTIONS_TRUTH_STATES={"current-live","watch-only-last-known","watch-only-no-history","no-snapshot"}

def _utc_iso(value:Any,label:str)->str:
    text=str(value or "").strip()
    if not text or len(text)>64:
        raise CanonicalDispatchError(f"{label} must be a bounded UTC timestamp")
    try:dt=datetime.fromisoformat(text.replace("Z","+00:00"))
    except Exception as e:raise CanonicalDispatchError(f"{label} is invalid") from e
    if dt.tzinfo is None:raise CanonicalDispatchError(f"{label} must include timezone")
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def validate_options_snapshot_arguments(args:Any,input_root:Path|None)->dict:
    if not isinstance(args,dict):raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE arguments must be object")
    exact(args,{"dataset","as_of_utc","risk_free_rate","snapshot_state","empty_reason","max_rows"},"OPTIONS_SNAPSHOT_ANALYZE arguments")
    if input_root is None:raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE requires governed input_root")
    resolved=resolve_dataset(input_root,"options_snapshot",args.get("dataset"))
    as_of=_utc_iso(args.get("as_of_utc"),"OPTIONS_SNAPSHOT_ANALYZE as_of_utc")
    try:risk_free=float(args.get("risk_free_rate",0.0))
    except Exception as e:raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE risk_free_rate must be numeric") from e
    if not -0.10<=risk_free<=0.50:raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE risk_free_rate must be within -0.10..0.50")
    state=str(args.get("snapshot_state") or "").strip()
    if state not in _OPTIONS_TRUTH_STATES:raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE snapshot_state is invalid")
    empty_reason=str(args.get("empty_reason") or "").strip()
    if len(empty_reason)>512:raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE empty_reason is too long")
    try:max_rows=int(args.get("max_rows",2000))
    except Exception as e:raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE max_rows must be integer") from e
    if not 1<=max_rows<=5000:raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE max_rows must be within 1..5000")
    return {
        "dataset":{k:resolved[k] for k in ("relative_path","sha256","bytes")},
        "as_of_utc":as_of,"risk_free_rate":risk_free,"snapshot_state":state,
        "empty_reason":empty_reason,"max_rows":max_rows,
    }


_NEWS_RUN_ID_RE=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

def validate_news_feature_sidecar_arguments(args:Any,input_root:Path|None,receipt_dir:Path|None)->dict:
    if not isinstance(args,dict):raise CanonicalDispatchError("NEWS_FEATURE_SIDECAR_BUILD arguments must be object")
    exact(args,{"articles","source_run_id","feature_asof_utc","feature_window_hours","max_article_rows"},"NEWS_FEATURE_SIDECAR_BUILD arguments")
    source_run_id=str(args.get("source_run_id") or "").strip()
    if not _NEWS_RUN_ID_RE.fullmatch(source_run_id):raise CanonicalDispatchError("NEWS_FEATURE_SIDECAR_BUILD source_run_id is invalid")
    feature_asof=_utc_iso(args.get("feature_asof_utc"),"NEWS_FEATURE_SIDECAR_BUILD feature_asof_utc")
    try:window=int(args.get("feature_window_hours",24))
    except Exception as e:raise CanonicalDispatchError("NEWS_FEATURE_SIDECAR_BUILD feature_window_hours must be integer") from e
    if not 1<=window<=168:raise CanonicalDispatchError("NEWS_FEATURE_SIDECAR_BUILD feature_window_hours must be within 1..168")
    try:max_rows=int(args.get("max_article_rows",20000))
    except Exception as e:raise CanonicalDispatchError("NEWS_FEATURE_SIDECAR_BUILD max_article_rows must be integer") from e
    if not 1<=max_rows<=20000:raise CanonicalDispatchError("NEWS_FEATURE_SIDECAR_BUILD max_article_rows must be within 1..20000")
    resolved=resolve_artifact_ref(input_root,receipt_dir,args.get("articles"),"NEWS_FEATURE_SIDECAR_BUILD articles")
    public_ref={k:resolved[k] for k in ("scope","relative_path","sha256","bytes")}
    if resolved.get("job_fingerprint") is not None:public_ref["job_fingerprint"]=resolved["job_fingerprint"]
    return {
        "articles":public_ref,
        "source_run_id":source_run_id,
        "feature_asof_utc":feature_asof,
        "feature_window_hours":window,
        "max_article_rows":max_rows,
    }

def validate_request(req:dict,root:Path,source_receipt:dict,input_root:Path|None=None,receipt_dir:Path|None=None)->dict:
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
    elif cid=="AUTOTUNER_CAMPAIGN":
        normalized_args=validate_autotuner_campaign_arguments(args,input_root)
    elif cid=="AUTOTUNER_PRIMARY_VALIDATION":
        normalized_args=validate_autotuner_primary_validation_arguments(args,input_root)
    elif cid=="CANONICAL_DATA_MATERIALIZE":
        normalized_args=validate_data_materialize_arguments(args,input_root)
    elif cid=="FEATURE_CONTRACT_VALIDATE":
        normalized_args=validate_feature_contract_arguments(args,input_root,receipt_dir)
    elif cid=="STRATEGY_PREVIEW":
        normalized_args=validate_strategy_preview_arguments(args,input_root,receipt_dir)
    elif cid=="MODEL_LAB_FIRST_CONSUMER":
        normalized_args=validate_model_lab_first_consumer_arguments(args,input_root)
    elif cid=="MODEL_LAB_COMPARE_VALIDATE":
        normalized_args=validate_model_lab_compare_validate_arguments(args,input_root)
    elif cid=="NEWS_REPLAY_ANALYZE":
        normalized_args=validate_news_replay_arguments(args,input_root)
    elif cid=="OPTIONS_SNAPSHOT_ANALYZE":
        normalized_args=validate_options_snapshot_arguments(args,input_root)
    elif cid=="NEWS_FEATURE_SIDECAR_BUILD":
        normalized_args=validate_news_feature_sidecar_arguments(args,input_root,receipt_dir)
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

def normalized_strategy_spec(root:Path,raw:dict)->dict:
    fn=private_callable(root,"autotuner_strategy_bridge.py","autotuner_strategy_bridge","normalize_strategy_spec")
    normalized=fn(raw)
    if not isinstance(normalized,dict) or not isinstance(normalized.get("strategy_spec"),dict):
        raise CanonicalDispatchError("canonical StrategySpec normalizer returned invalid contract")
    digest=str(normalized.get("strategy_spec_digest") or "")
    if not _SHA256.fullmatch(digest):raise CanonicalDispatchError("canonical StrategySpec digest is invalid")
    spec=normalized["strategy_spec"]
    if not str(spec.get("strategy_id") or "").strip():
        raise CanonicalDispatchError("canonical StrategySpec strategy_id is missing")
    if not str(spec.get("symbol") or "").strip():
        raise CanonicalDispatchError("canonical StrategySpec symbol is missing")
    if not str(spec.get("timeframe") or "").strip():
        raise CanonicalDispatchError("canonical StrategySpec timeframe is missing")
    return normalized

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

def copy_crw_evidence_artifacts(raw:dict,root:Path,artifact_root:Path|None)->dict[str,dict]:
    if artifact_root is None:return {}
    rel=str(raw.get("artifact_dir") or "").strip()
    if not rel:raise CanonicalDispatchError("canonical CRW backtest artifact_dir is missing")
    source=(root/rel).resolve(); source_root=root.resolve()
    if source_root not in source.parents or not source.is_dir():
        raise CanonicalDispatchError("canonical CRW artifact directory is missing or outside private source root")
    allowed=(
        "trade_rows.csv",
        "condition_event_rows.csv",
        "simulation_trade_rows.csv",
        "simulation_condition_event_rows.csv",
        "dca_fill_rows.csv",
    )
    out={}
    dest_root=(artifact_root/"crw_evidence").resolve();dest_root.mkdir(parents=True,exist_ok=True)
    for name in allowed:
        src=(source/name).resolve()
        if source not in src.parents or not src.is_file():
            raise CanonicalDispatchError(f"canonical CRW evidence artifact missing: {name}")
        dest=dest_root/name
        shutil.copyfile(src,dest)
        desc=artifact_descriptor(dest,artifact_root)
        try:
            with dest.open("r",encoding="utf-8-sig",newline="") as handle:
                count=sum(1 for _ in csv.DictReader(handle))
        except Exception as e:
            raise CanonicalDispatchError(f"canonical CRW evidence artifact unreadable: {name}") from e
        out[name.removesuffix(".csv")]={**desc,"format":"csv","row_count":count}
    return out

def sanitize_symbol_support(raw:dict)->list[dict]:
    keys=(
        "symbol","status","bar_count","event_count","total_trades","closed_trade_count",
        "open_trade_count","open_trade_mark_to_market","win_rate","profit_factor","gross_pnl",
        "net_pnl","max_drawdown","exposure","entry_level","exit_level","dca_enabled",
        "dca_tier_drawdowns_pct","dca_max_adds","dca_base_qty","dca_max_contracts",
        "dca_trigger_mode","tv_net_pnl","simulated_net_pnl","simulated_minus_tv_net_pnl",
    )
    out=[]
    for row in raw.get("symbol_rows") or []:
        if not isinstance(row,dict):continue
        cleaned={key:deepcopy(row.get(key)) for key in keys if key in row}
        views=row.get("execution_views")
        if isinstance(views,dict):cleaned["execution_views"]=deepcopy(views)
        out.append(cleaned)
    return out

def sanitize_crw_result(raw:dict,args:dict,root:Path|None=None,artifact_root:Path|None=None)->dict:
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
    persisted=copy_crw_evidence_artifacts(raw,root,artifact_root) if root is not None else {}
    persisted_artifacts=[dict(node) for node in persisted.values()]
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
        "symbol_support":sanitize_symbol_support(raw),
        "governed_inputs":deepcopy(input_map),
        "raw_result_sha256":sha(raw),
        "row_artifact_sha256":{
            name:(persisted[name]["sha256"] if name in persisted else sha(rows))
            for name,rows in row_sets.items()
        },
        "row_artifact_counts":{
            name:(persisted[name]["row_count"] if name in persisted else len(rows))
            for name,rows in row_sets.items()
        },
        "row_artifacts":persisted,
        "artifacts":persisted_artifacts,
        "safety":expected,
    }
    return result
def sanitize_public_tree(value:Any)->Any:
    if isinstance(value,dict):
        out={}
        for key,node in value.items():
            low=str(key).lower()
            if low=="artifact_dir" or low.endswith("_path") or low in {"source_path","dataset_path"}:
                continue
            if low=="error" and isinstance(node,str):
                out["error_class"]=node.split(":",1)[0][:128] if node else None
                continue
            out[key]=sanitize_public_tree(node)
        return out
    if isinstance(value,list):return [sanitize_public_tree(node) for node in value]
    return value

def governed_autotuner_backtest_runner(root:Path,dataset_path:Path,strategy_spec:dict):
    runner=private_callable(root,"strategy_backtest_registry.py","strategy_backtest_registry","run_strategy_backtest")
    nested=strategy_spec.get("strategy_spec") if isinstance(strategy_spec.get("strategy_spec"),dict) else strategy_spec
    symbol=str(nested.get("symbol") or strategy_spec.get("symbol") or "").upper()
    asset_type=str(nested.get("asset_type") or strategy_spec.get("asset_type") or "futures")
    def run(payload:dict,_data_root:Path):
        node=deepcopy(payload)
        node["_verified_source_paths"]={symbol:str(dataset_path)}
        node["asset_type"]=asset_type
        return runner(node,dataset_path.parent)
    return run

def autotuner_campaign_dependencies(root:Path)->dict[str,str]:
    paths=(
        "autotuner_campaign_runner.py","autotuner_campaign_planner.py","autotuner_parameter_consumption.py",
        "autotuner_strategy_bridge.py","strategy_backtest_registry.py","strategies/python/crw_score_multi_mode.py",
    )
    return {path:private_blob_identity(root,path) for path in paths}

def autotuner_validation_dependencies(root:Path)->dict[str,str]:
    paths=(
        "autotuner_primary_validation_runner.py","autotuner_strategy_bridge.py",
        "strategy_backtest_registry.py","model_lab_validation.py",
    )
    return {path:private_blob_identity(root,path) for path in paths}

def model_lab_first_consumer_dependencies(root:Path)->dict[str,str]:
    paths=(
        "scripts/operator/model_lab_xgboost_first_consumer.py","model_lab_training_matrix.py",
        "model_lab_canonical_data.py","model_lab_xgboost.py","model_lab_canonical_trainer.py",
        "model_lab_validation.py","feature_contract.py","predictive_target_spec.py",
    )
    return {path:private_blob_identity(root,path) for path in paths}

def execute_model_lab_first_consumer(v:dict,root:Path,input_root:Path,fn)->dict:
    args=v["arguments"]; resolved={}
    for name in ("raw","features","feature_sidecar"):
        resolved[name]=resolve_dataset(input_root,f"model_lab_{name}",args["inputs"][name])
    symbol=args["symbol"]
    stored_symbol=symbol[:-2] if args["asset_type"]=="futures" and symbol.endswith("1!") else symbol
    if args["asset_type"]=="futures" and stored_symbol.endswith("-CONTINUOUS"):
        stored_symbol=stored_symbol[:-11]
    if not stored_symbol or not _SYMBOL.fullmatch(stored_symbol):
        raise CanonicalDispatchError("MODEL_LAB_FIRST_CONSUMER canonical symbol is invalid")
    staging=Path(tempfile.mkdtemp(prefix="mmibkr-model-lab-first-consumer-"))
    try:
        directory=(staging/"futures"/f"{stored_symbol}-CONTINUOUS") if args["asset_type"]=="futures" else (staging/"stocks"/stored_symbol)
        directory.mkdir(parents=True,exist_ok=True)
        raw_path=directory/f"{args['timeframe']}.csv"
        feature_path=directory/f"{args['timeframe']}.features.csv"
        sidecar_path=feature_path.with_suffix(feature_path.suffix+".manifest.json")
        for src,dst in ((resolved["raw"]["path"],raw_path),(resolved["features"]["path"],feature_path),(resolved["feature_sidecar"]["path"],sidecar_path)):
            shutil.copyfile(src,dst)
        ns=argparse.Namespace(
            data_root=str(staging),asset_type=args["asset_type"],symbol=symbol,timeframe=args["timeframe"],
            horizon_bars=args["horizon_bars"],target_name=args["target_name"],start_year=args["start_year"],
            test_span_years=args["test_span_years"],min_test_rows=args["min_test_rows"],output=None,
        )
        raw=fn(ns)
        if not isinstance(raw,dict) or raw.get("schema")!="mm.model_lab_xgboost_first_consumer.v1":
            raise CanonicalDispatchError("canonical Model Lab first consumer returned invalid contract")
        safety=raw.get("safety")
        expected={
            "read_only":True,"runtime_authority":False,"strategy_spec_authority":False,
            "promotion_authority":False,"order_submission":False,"live_trading_change":False,
        }
        if not isinstance(safety,dict) or any(safety.get(key) is not value for key,value in expected.items()):
            raise CanonicalDispatchError("Model Lab first consumer safety contract rejected")
        economic=raw.get("economic_evidence")
        if not isinstance(economic,dict) or economic.get("status")!="EVIDENCE_GAP" or economic.get("promotion_allowed") is not False:
            raise CanonicalDispatchError("Model Lab first consumer economic-evidence boundary rejected")
        public=sanitize_public_tree(raw)
        public["governed_inputs"]={
            name:{k:resolved[name][k] for k in ("relative_path","sha256","bytes")}
            for name in ("raw","features","feature_sidecar")
        }
        public["canonical_dependencies"]=model_lab_first_consumer_dependencies(root)
        return public
    finally:
        shutil.rmtree(staging,ignore_errors=True)


def model_lab_compare_validate_dependencies(root:Path)->dict[str,str]:
    paths=("model_lab_comparison_matrix.py","model_lab_validation.py")
    return {path:private_blob_identity(root,path) for path in paths}

def execute_model_lab_compare_validate(v:dict,root:Path,input_root:Path,fn)->dict:
    args=v["arguments"]; resolved={}
    for name in ("incumbent_matrix","challenger_matrix"):
        resolved[name]=resolve_dataset(input_root,f"model_lab_{name}",args["inputs"][name])
    module=sys.modules.get(getattr(fn,"__module__",""))
    pd=getattr(module,"pd",None)
    read_csv=getattr(pd,"read_csv",None)
    if not callable(read_csv):raise CanonicalDispatchError("MODEL_LAB_COMPARE_VALIDATE canonical comparison owner does not expose pandas CSV loading")
    incumbent=read_csv(resolved["incumbent_matrix"]["path"])
    challenger=read_csv(resolved["challenger_matrix"]["path"])
    raw=fn(
        incumbent,challenger,
        target_name=args["target_name"],
        target_identity=args["target_identity"],
        min_shared_rows=args["min_shared_rows"],
    )
    if not isinstance(raw,tuple) or len(raw)!=3 or not isinstance(raw[2],dict):
        raise CanonicalDispatchError("canonical Model Lab comparison returned invalid contract")
    incumbent_aligned,challenger_aligned,alignment=raw
    if alignment.get("schema")!="mm.model_lab_comparison_alignment_evidence.v1":
        raise CanonicalDispatchError("canonical Model Lab comparison evidence schema rejected")
    if alignment.get("target_identity")!=args["target_identity"] or alignment.get("target_name")!=args["target_name"]:
        raise CanonicalDispatchError("canonical Model Lab comparison target identity mismatch")
    if alignment.get("target_exact_match") is not True or int(alignment.get("shared_rows") or 0)<args["min_shared_rows"]:
        raise CanonicalDispatchError("canonical Model Lab comparison shared target contract rejected")
    expected_safety={
        "feature_recompute":False,"target_recompute":False,"resample":False,
        "fill_or_backfill":False,"row_reorder":False,"order_submission":False,
    }
    safety=alignment.get("safety")
    if not isinstance(safety,dict) or any(safety.get(key) is not value for key,value in expected_safety.items()):
        raise CanonicalDispatchError("canonical Model Lab comparison safety contract rejected")
    try:timestamps=incumbent_aligned["timestamp"]
    except Exception as e:raise CanonicalDispatchError("canonical Model Lab comparison aligned timestamps missing") from e
    splitter=private_callable(root,"model_lab_validation.py","model_lab_validation","non_overlapping_purged_walk_forward_splits")
    manifest_fn=private_callable(root,"model_lab_validation.py","model_lab_validation","split_manifest")
    require_target=private_callable(root,"model_lab_validation.py","model_lab_validation","require_target_safe_validation")
    splits=splitter(
        timestamps,start_year=args["start_year"],test_span_years=args["test_span_years"],
        embargo_bars=args["embargo_bars"],purge_bars=args["purge_bars"],min_test_rows=args["min_test_rows"],
    )
    manifest=manifest_fn(
        splits,contract="canonical_nonoverlap_purged_compare",
        embargo_bars=args["embargo_bars"],purge_bars=args["purge_bars"],test_span_years=args["test_span_years"],
    )
    target=argparse.Namespace(
        horizon_bars=args["horizon_bars"],identity=args["target_identity"],leakage_guard="embargo_and_purge",
    )
    target_validation=require_target(manifest,target)
    if target_validation.get("leakage_safe") is not True:
        raise CanonicalDispatchError("canonical Model Lab target validation is not leakage safe")
    public_alignment=sanitize_public_tree(alignment)
    return {
        "schema":"mmibkr.model_lab_compare_validate.v1",
        "alignment":public_alignment,
        "walk_forward_validation":sanitize_public_tree(manifest),
        "target_validation":sanitize_public_tree(target_validation),
        "governed_inputs":{
            name:{k:resolved[name][k] for k in ("relative_path","sha256","bytes")}
            for name in ("incumbent_matrix","challenger_matrix")
        },
        "canonical_dependencies":model_lab_compare_validate_dependencies(root),
        "safety":{
            "read_only":True,"feature_recompute":False,"target_recompute":False,"training":False,
            "model_promotion":False,"strategy_spec_write":False,"runtime_activation":False,
            "order_submission":False,"live_trading_change":False,
        },
    }

def preview_data_quality(row:dict)->dict:
    fatal=[];warnings=[]
    def num(name:str):
        try:
            value=row.get(name)
            if value is None or value=="":return None
            value=float(value)
            if not (value==value and value not in (float("inf"),float("-inf"))):return None
            return value
        except Exception:return None
    for name in ("open","high","low","close"):
        value=num(name)
        if value is None:fatal.append(f"{name} missing_or_non_numeric")
        elif value<=0:fatal.append(f"{name} <= 0")
    volume=num("volume")
    if volume is None:warnings.append("volume missing_or_non_numeric")
    elif volume<=0:fatal.append("volume <= 0")
    bar_count=num("barCount")
    if bar_count is not None and bar_count<=0:warnings.append("barCount <= 0")
    vwap=num("VWAP")
    if vwap is None:warnings.append("VWAP missing")
    elif vwap<=0:warnings.append("VWAP <= 0")
    return {"status":"blocked" if fatal else "ok","execution_safe":not fatal,"fatal_reasons":fatal,"warnings":warnings}

def select_preview_row(frame:Any,policy:str,lookback:int)->tuple[dict,dict,dict]:
    if frame is None or getattr(frame,"empty",True):raise CanonicalDispatchError("STRATEGY_PREVIEW feature artifact is empty")
    latest=dict(frame.iloc[-1].to_dict())
    latest_quality=preview_data_quality(latest)
    selection={
        "policy":policy,
        "used_fallback_row":False,
        "latest_feature_timestamp":latest.get("timestamp") or latest.get("ts"),
        "selected_feature_timestamp":latest.get("timestamp") or latest.get("ts"),
        "zero_volume_rows_skipped":0,
        "lookback_rows":lookback,
        "warnings":[],
        "blockers":[],
    }
    if policy=="latest" or latest_quality.get("execution_safe") is True:
        return latest,latest_quality,selection
    fatal=[str(x) for x in latest_quality.get("fatal_reasons") or []]
    latest_only_volume=bool(fatal) and all(x=="volume <= 0" for x in fatal)
    if policy!="latest_execution_safe" or not latest_only_volume:
        selection["blockers"].append("latest_row_not_execution_safe")
        return latest,latest_quality,selection
    skipped=0
    rows=frame.tail(max(1,lookback)).to_dict(orient="records")
    for candidate in reversed(rows):
        candidate=dict(candidate or {})
        quality=preview_data_quality(candidate)
        if quality.get("execution_safe") is True:
            selection.update({
                "used_fallback_row":True,
                "selected_feature_timestamp":candidate.get("timestamp") or candidate.get("ts"),
                "zero_volume_rows_skipped":skipped,
                "warnings":["latest_zero_volume_bar_skipped","selected_recent_positive_volume_feature_row"],
                "candidate_data_quality":quality,
            })
            quality=dict(quality)
            quality["status"]="ok_with_warnings"
            quality["warnings"]=list(dict.fromkeys(list(quality.get("warnings") or [])+selection["warnings"]))
            quality["feature_selection"]=selection
            quality["latest_row_data_quality"]=latest_quality
            return candidate,quality,selection
        cfatal=[str(x) for x in quality.get("fatal_reasons") or []]
        if cfatal and all(x=="volume <= 0" for x in cfatal):skipped+=1
    selection["blockers"].append("no_recent_execution_safe_feature_row")
    selection["zero_volume_rows_skipped"]=skipped
    latest_quality=dict(latest_quality);latest_quality["feature_selection"]=selection
    return latest,latest_quality,selection

def preview_condition_rows(block:dict)->list[dict]:
    rows=[]
    for item in (block or {}).get("items") or []:
        if isinstance(item,dict):
            rows.append({
                "id":item.get("id"),"label":item.get("label"),"left":item.get("left"),
                "left_value":item.get("left_value"),"operator":item.get("operator"),
                "right_param":item.get("right_param"),"right_value":item.get("right_value"),
                "enabled":item.get("enabled",True),"passed":bool(item.get("passed")),
            })
    return rows

def strategy_preview_dependencies(root:Path)->dict[str,str]:
    paths=[
        "autotuner_strategy_bridge.py","feature_contract.py","strategies/__init__.py",
        "strategies/event_bus.py","strategy_builder_condition_contract_14th31kn.py",
    ]
    out={}
    for path in paths:
        target=(root/path).resolve()
        if target.is_file():out[path]=private_blob_identity(root,path)
    return out

def execute_strategy_preview(v:dict,root:Path,input_root:Path|None,receipt_dir:Path|None)->dict:
    args=v["arguments"]
    resolved=resolve_artifact_ref(input_root,receipt_dir,args["feature_artifact"],"feature_artifact")
    sidecar_fn=private_callable(root,"feature_contract.py","feature_contract","read_feature_artifact_sidecar")
    sidecar=sidecar_fn(resolved["path"],verify_artifact=True)
    if not isinstance(sidecar,dict):raise CanonicalDispatchError("STRATEGY_PREVIEW feature sidecar validation failed")
    manifest=sidecar.get("feature_manifest")
    if not isinstance(manifest,dict):raise CanonicalDispatchError("STRATEGY_PREVIEW feature manifest missing")
    manifest_hash=str(sidecar.get("feature_manifest_hash") or manifest.get("manifest_hash") or "").lower()
    semantic_hash=str(manifest.get("feature_semantic_hash") or "").lower()
    if not _SHA256.fullmatch(manifest_hash) or not _SHA256.fullmatch(semantic_hash):
        raise CanonicalDispatchError("STRATEGY_PREVIEW feature manifest identities are invalid")
    if args.get("expected_feature_semantic_hash") and args["expected_feature_semantic_hash"]!=semantic_hash:
        raise CanonicalDispatchError("STRATEGY_PREVIEW feature semantic hash mismatch")
    normalized=normalized_strategy_spec(root,args["strategy_spec"]); spec=normalized["strategy_spec"]
    symbol=str(spec.get("symbol") or "").strip().upper(); timeframe=str(spec.get("timeframe") or "").strip()
    manifest_symbols=[str(x).strip().upper() for x in manifest.get("symbol_universe") or [] if str(x).strip()]
    manifest_tfs=[str(x).strip() for x in manifest.get("target_timeframes") or [] if str(x).strip()]
    if manifest_symbols and symbol not in manifest_symbols:
        raise CanonicalDispatchError("STRATEGY_PREVIEW StrategySpec symbol is not present in feature manifest")
    if manifest_tfs and timeframe not in manifest_tfs:
        raise CanonicalDispatchError("STRATEGY_PREVIEW StrategySpec timeframe is not present in feature manifest")
    try:pd=importlib.import_module("pandas")
    except Exception as e:raise CanonicalDispatchError("STRATEGY_PREVIEW requires pandas runtime dependency") from e
    frame=pd.read_csv(resolved["path"])
    selected,quality,selection=select_preview_row(frame,args["row_policy"],args["lookback_rows"])
    create=load_callable(root,CAPABILITIES["STRATEGY_PREVIEW"])
    definition_fn=private_callable(root,"strategies/event_bus.py","strategies.event_bus","build_strategy_definition")
    parameters=dict(spec.get("parameters") or {})
    strategy_id=str(spec.get("strategy_id") or "").strip()
    definition=definition_fn(strategy_id,{
        **parameters,
        "symbol":symbol,
        "source_symbol":symbol,
        "symbol_universe":[symbol],
        "timeframe":timeframe,
        "source_timeframe":timeframe,
        "asset_type":spec.get("asset_type") or "stocks",
        "dataset_identity":{"feature_manifest_hash":manifest_hash,"feature_semantic_hash":semantic_hash},
    })
    strategy_obj=create(strategy_id,config=parameters)
    signal_name,meta=strategy_obj.evaluate(pd.DataFrame([selected]))
    meta=meta if isinstance(meta,dict) else {}
    if strategy_id!="crw_score_multi_mode":
        builder_module_path=root/"strategy_builder_condition_contract_14th31kn.py"
        if builder_module_path.is_file():
            get_contract=private_callable(root,"strategy_builder_condition_contract_14th31kn.py","strategy_builder_condition_contract_14th31kn","builder_condition_contract_from_payload")
            eval_contract=private_callable(root,"strategy_builder_condition_contract_14th31kn.py","strategy_builder_condition_contract_14th31kn","evaluate_builder_condition_contract")
            contract=get_contract({"strategy_spec":spec})
            if contract:
                native_signal=signal_name;native_meta=dict(meta)
                builder_eval=eval_contract(contract,feature_values=selected,context_values=args["context_values"])
                if not isinstance(builder_eval,dict):raise CanonicalDispatchError("builder condition evaluator returned invalid contract")
                signal_name=(builder_eval.get("signal") or "HOLD") if builder_eval.get("evaluation_ready") else "HOLD"
                meta={
                    **native_meta,
                    "reason":builder_eval.get("reason_code"),
                    "builder_condition_execution":builder_eval,
                    "builder_condition_contract_hash":contract.get("contract_hash"),
                    "native_registry_evaluation":{"signal":native_signal,"meta":native_meta},
                    "builder_condition_signal_override":True,
                }
    conditions=meta.get("conditions") if isinstance(meta.get("conditions"),dict) else {}
    required=list(getattr(definition,"required_indicators",[]) or [])
    missing=[name for name in required if name not in selected]
    builder_execution=meta.get("builder_condition_execution") if isinstance(meta.get("builder_condition_execution"),dict) else {}
    for name in builder_execution.get("missing_indicators") or []:
        if name not in missing:missing.append(name)
    current_values=conditions.get("current_values") if isinstance(conditions.get("current_values"),dict) else {}
    snapshot={}
    for key in ("close","Z_CLOSE_20","Z_VOLUME_20","ATR","RSI","MFI","VWAP"):
        if key in selected and selected.get(key) is not None:snapshot[key]=selected.get(key)
    artifact_ref=dict(args["feature_artifact"])
    return {
        "schema":"mmibkr.strategy_preview.v1",
        "strategy_spec_digest":normalized["strategy_spec_digest"],
        "strategy":{
            "strategy_id":strategy_id,
            "version":getattr(definition,"version",None),
            "parameters":getattr(definition,"parameters",{}) or parameters,
            "parameter_schema":meta.get("parameter_schema") or getattr(strategy_obj,"parameter_schema",lambda:{})(),
            "condition_spec":meta.get("condition_spec") or getattr(strategy_obj,"condition_spec",lambda:{})(),
            "required_indicators":required,
            "present_indicators":[name for name in required if name in selected],
            "missing_indicators":missing,
            "warmup_bars":getattr(definition,"warmup_bars",None),
        },
        "feature_artifact":artifact_ref,
        "feature_manifest_hash":manifest_hash,
        "feature_semantic_hash":semantic_hash,
        "row_selection":selection,
        "data_quality":quality,
        "conditions":{
            "entry_long":conditions.get("entry_long") or {},
            "exit_long":conditions.get("exit_long") or {},
            "entry_rows":preview_condition_rows(conditions.get("entry_long") or {}),
            "exit_rows":preview_condition_rows(conditions.get("exit_long") or {}),
        },
        "builder_condition_execution":builder_execution,
        "signal":{
            "raw_signal":signal_name or "HOLD",
            "reason":meta.get("reason"),
            "indicator_snapshot":snapshot,
        },
        "context_values_sha256":sha(args["context_values"]),
        "canonical_dependencies":strategy_preview_dependencies(root),
        "safety":{
            "research_preview_only":True,
            "position_snapshot_used":False,
            "risk_preview_used":False,
            "sizing_preview_used":False,
            "broker_preview_used":False,
            "order_intent_emitted":False,
            "broker_submit":False,
            "broker_cancel":False,
            "broker_flatten":False,
            "runtime_activation":False,
            "live_trading":False,
        },
    }

def validate_feature_contract(v:dict,root:Path,input_root:Path|None,receipt_dir:Path|None)->dict:
    args=v["arguments"]
    resolved=resolve_artifact_ref(input_root,receipt_dir,args["feature_artifact"],"feature_artifact")
    fn=load_callable(root,CAPABILITIES["FEATURE_CONTRACT_VALIDATE"])
    raw=fn(resolved["path"],verify_artifact=True)
    if not isinstance(raw,dict):raise CanonicalDispatchError("canonical feature sidecar validator returned invalid contract")
    manifest=raw.get("feature_manifest")
    if not isinstance(manifest,dict):raise CanonicalDispatchError("canonical feature sidecar is missing feature_manifest")
    manifest_hash=str(raw.get("feature_manifest_hash") or manifest.get("manifest_hash") or "").lower()
    semantic_hash=str(manifest.get("feature_semantic_hash") or "").lower()
    if not _SHA256.fullmatch(manifest_hash):raise CanonicalDispatchError("canonical feature manifest hash is invalid")
    if not _SHA256.fullmatch(semantic_hash):raise CanonicalDispatchError("canonical feature semantic hash is invalid")
    if args.get("expected_manifest_hash") and args["expected_manifest_hash"]!=manifest_hash:
        raise CanonicalDispatchError("FEATURE_CONTRACT_VALIDATE manifest hash mismatch")
    if args.get("expected_semantic_hash") and args["expected_semantic_hash"]!=semantic_hash:
        raise CanonicalDispatchError("FEATURE_CONTRACT_VALIDATE semantic hash mismatch")
    features=manifest.get("features") if isinstance(manifest.get("features"),list) else []
    feature_columns=[]
    feature_ids=[]
    for row in features:
        if not isinstance(row,dict):continue
        column=str(row.get("output_column") or "").strip()
        identity=str(row.get("identity_hash") or "").strip()
        if column:feature_columns.append(column)
        if identity:feature_ids.append(identity)
    source_identity=manifest.get("source_dataset_identity")
    return {
        "schema":"mmibkr.feature_contract_validation.v1",
        "feature_artifact":dict(args["feature_artifact"]),
        "feature_manifest_hash":manifest_hash,
        "feature_semantic_hash":semantic_hash,
        "contract_version":manifest.get("contract_version"),
        "feature_contract_mode":manifest.get("feature_contract_mode"),
        "causal":manifest.get("causal") is True,
        "feature_count":len(features),
        "feature_columns":feature_columns,
        "feature_identity_hashes":feature_ids,
        "symbol_universe":list(manifest.get("symbol_universe") or []),
        "source_timeframes":list(manifest.get("source_timeframes") or []),
        "target_timeframes":list(manifest.get("target_timeframes") or []),
        "label_target_columns_excluded":list(manifest.get("label_target_columns_excluded") or []),
        "generation_identity":manifest.get("generation_identity"),
        "consumer_identity":manifest.get("consumer_identity"),
        "source_dataset_identity_sha256":sha(source_identity if isinstance(source_identity,dict) else {}),
        "canonical_dependencies":{
            "feature_contract.py":private_blob_identity(root,"feature_contract.py"),
        },
        "safety":{
            "artifact_read_only":True,
            "broker_submit":False,
            "broker_cancel":False,
            "broker_flatten":False,
            "runtime_activation":False,
            "live_trading":False,
        },
    }

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


def news_replay_dependencies(root:Path)->dict[str,str]:
    return {
        "news_engine.py":private_blob_identity(root,"news_engine.py"),
        "news_publication_time.py":private_blob_identity(root,"news_publication_time.py"),
        "scripts/operator/news_replay_probe_14nf.py":private_blob_identity(root,"scripts/operator/news_replay_probe_14nf.py"),
    }

def _news_public_article(row:dict)->dict:
    allowed=(
        "id","symbol","title","url","source","published_at","mention_count","source_domain",
        "match_method","match_confidence","relevance_class","relevance_label","relevance_action",
        "relevance_weight","macro_spillover","sentiment_score","sentiment_label",
        "deterministic_sentiment","impact_score","deterministic_impact","confidence",
        "deterministic_confidence","article_quality_score","score","final_score","themes",
        "summary","summary_source","symbol_relevance_reason","pos_hits","neg_hits",
        "source_type","provider","provider_code","provider_article_id","ibkr_provider_code",
        "ibkr_article_id","provider_sentiment_score","provider_impact_score","provider_confidence",
        "deterministic_score_raw","blended_score",
    )
    return {key:deepcopy(row.get(key)) for key in allowed if key in row}

def execute_news_replay(v:dict,root:Path,input_root:Path|None,artifact_root:Path|None,engine_cls:Any)->dict:
    if input_root is None:
        raise CanonicalDispatchError("NEWS_REPLAY_ANALYZE requires governed input_root")
    if artifact_root is None:
        raise CanonicalDispatchError("NEWS_REPLAY_ANALYZE requires receipt_dir artifact storage")
    args=v["arguments"]; descriptor=resolve_dataset(input_root,"news_replay",args["dataset"])
    try:
        payload=json.loads(descriptor["path"].read_text(encoding="utf-8"))
    except Exception as e:
        raise CanonicalDispatchError("NEWS_REPLAY_ANALYZE dataset must be valid JSON") from e
    if isinstance(payload,dict):
        payload=payload.get("items") if isinstance(payload.get("items"),list) else payload.get("articles")
    if not isinstance(payload,list):
        raise CanonicalDispatchError("NEWS_REPLAY_ANALYZE dataset must be a JSON list or object containing items/articles list")
    if len(payload)>args["max_items"]:
        raw_items=payload[:args["max_items"]]
    else:
        raw_items=payload
    config={
        "NEWS_SYMBOL_UNIVERSE":list(args["symbols"]),
        "NEWS_SYMBOL_ALIASES":deepcopy(args["symbol_aliases"]),
        "NEWS_THEME_TICKER_MAP":deepcopy(args["theme_ticker_map"]),
        "NEWS_LABELED_ALLOW_OUTSIDE_UNIVERSE":False,
        "NEWS_LLM_ENABLED":False,
        "NEWS_MAX_TOTAL_ARTICLES_PER_RUN":args["max_items"],
        "NEWS_MAX_ARTICLES_PER_RUN":args["max_items"],
    }
    work_root=(artifact_root/"news_work").resolve()
    engine=engine_cls(config,work_root)
    normalized=[]
    for raw in raw_items:
        if not isinstance(raw,dict):continue
        node=engine._normalize_raw_item(raw)
        if isinstance(node,dict):normalized.append(node)
    symbols=engine._load_symbol_universe()
    aliases=engine._load_symbol_aliases()
    themes=engine._load_theme_ticker_map()
    universe=set(symbols)
    patterns=engine._build_symbol_patterns(universe)
    alias_patterns=engine._build_alias_patterns(aliases,universe)
    mapped,match_stats=engine._compile_articles(
        normalized,patterns,alias_patterns,aliases,themes,universe,args["max_items"],
    )
    sentiment_by_symbol={}
    full_articles=[]
    for symbol,rows in mapped.items():
        enriched=[]
        for row in rows:
            combined=f"{row.get('title','')} {row.get('text_snip','')}".strip()
            sentiment,label,pos,neg=engine._score_sentiment(combined)
            impact=engine._score_impact(combined,int(row.get("mention_count") or 0),str(row.get("source_domain") or ""))
            confidence=engine._score_confidence(combined,int(row.get("mention_count") or 0),str(row.get("source_domain") or ""))
            relevance=engine._relevance_profile(
                str(row.get("match_method") or ""),
                int(row.get("mention_count") or 0),
                row.get("match_confidence"),
            )
            quality=engine._article_quality_score(sentiment,impact,confidence)
            score=round(float(quality)*float(relevance.get("relevance_weight") or 0),2)
            node={
                **row,**relevance,
                "sentiment_score":sentiment,"sentiment_label":label,"deterministic_sentiment":sentiment,
                "impact_score":impact,"deterministic_impact":impact,
                "confidence":confidence,"deterministic_confidence":confidence,
                "article_quality_score":quality,"score":score,"final_score":score,
                "themes":engine._themes_for_text(combined),
                "summary":engine._deterministic_summary(str(row.get("title") or ""),str(row.get("text_snip") or "")),
                "summary_source":"deterministic","pos_hits":pos,"neg_hits":neg,
                "llm_sentiment":None,"llm_impact":None,"llm_confidence":None,
                "llm_sentiment_raw":None,"llm_impact_raw":None,"llm_confidence_raw":None,"llm_score_raw":None,
                "disagreement_flag":False,
            }
            node["symbol_relevance_reason"]=engine._symbol_relevance_reason(node)
            node.update(engine._comparison_fields(node))
            public=_news_public_article(node)
            enriched.append(public);full_articles.append(public)
        sentiment_by_symbol[symbol]=enriched
    scorecards=engine._generate_scorecards(sentiment_by_symbol)
    for row in scorecards:
        row.pop("updated_at",None)
    unmatched=[
        {key:deepcopy(row.get(key)) for key in ("title","url","source","published_at") if key in row}
        for row in (match_stats.get("unmatched_items") or [])
        if isinstance(row,dict)
    ]
    evidence_root=(artifact_root/"news_replay").resolve();evidence_root.mkdir(parents=True,exist_ok=True)
    artifact_payloads={
        "articles.json":full_articles,
        "scorecards.json":scorecards,
        "unmatched.json":unmatched,
        "match_summary.json":{
            "matched_items_total":int(match_stats.get("matched_items_total") or 0),
            "unmatched_items_total":int(match_stats.get("unmatched_items_total") or 0),
            "top_unmatched_entities":deepcopy(match_stats.get("top_unmatched_entities") or []),
        },
    }
    artifacts=[]
    artifact_map={}
    for name,node in artifact_payloads.items():
        target=evidence_root/name
        target.write_text(json.dumps(node,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False,default=str)+"\n",encoding="utf-8")
        desc=artifact_descriptor(target,artifact_root);artifacts.append(desc);artifact_map[name]=desc
    shutil.rmtree(work_root,ignore_errors=True)
    return {
        "schema":"mmibkr.news_replay_analysis.v1",
        "dataset":{k:descriptor[k] for k in ("relative_path","sha256","bytes")},
        "symbols":list(args["symbols"]),
        "input_item_count":len(payload),
        "bounded_item_count":len(raw_items),
        "normalized_item_count":len(normalized),
        "matched_item_count":int(match_stats.get("matched_items_total") or 0),
        "unmatched_item_count":int(match_stats.get("unmatched_items_total") or 0),
        "matched_article_symbol_rows":len(full_articles),
        "scorecard_count":len(scorecards),
        "scorecards":deepcopy(scorecards[:50]),
        "scorecards_sha256":sha(scorecards),
        "articles_sha256":sha(full_articles),
        "top_unmatched_entities":deepcopy(match_stats.get("top_unmatched_entities") or []),
        "artifact_map":artifact_map,
        "artifacts":artifacts,
        "canonical_dependencies":news_replay_dependencies(root),
        "policy":{
            "deterministic_only":True,
            "cross_run_dedupe_applied":False,
            "provider_or_rss_acquisition":False,
            "llm_enrichment":False,
            "labeled_outside_universe":False,
        },
        "safety":{
            "research_only":True,
            "network_acquisition":False,
            "broker_submit":False,
            "broker_cancel":False,
            "broker_flatten":False,
            "strategy_spec_write":False,
            "runtime_activation":False,
            "promotion_mutation":False,
            "live_trading":False,
        },
    }


def options_snapshot_dependencies(root:Path)->dict[str,str]:
    return {"options_scanner.py":private_blob_identity(root,"options_scanner.py")}

def _finite_number(value:Any)->float|None:
    if value in (None,""):return None
    try:number=float(value)
    except Exception:return None
    if number!=number or number in (float("inf"),float("-inf")):return None
    return number

def _options_expiry_utc(row:dict)->tuple[datetime|None,str,str]:
    exact_time=str(row.get("expiry_utc") or "").strip()
    if exact_time:
        try:
            dt=datetime.fromisoformat(exact_time.replace("Z","+00:00"))
            if dt.tzinfo is None:return None,"","expiry_utc_missing_timezone"
            utc=dt.astimezone(timezone.utc)
            return utc,utc.isoformat().replace("+00:00","Z"),"exact"
        except Exception:return None,"","expiry_utc_invalid"
    raw=str(row.get("expiry") or row.get("lastTradeDateOrContractMonth") or "").strip()
    if not re.fullmatch(r"\d{8}",raw):return None,"","expiry_invalid"
    try:dt=datetime.strptime(raw,"%Y%m%d").replace(hour=23,minute=59,second=59,tzinfo=timezone.utc)
    except Exception:return None,"","expiry_invalid"
    return dt,dt.isoformat().replace("+00:00","Z"),"end_of_utc_day_assumption"

def _options_quote_basis(row:dict)->tuple[float,str,float,float,float]:
    bid=max(0.0,_finite_number(row.get("bid")) or 0.0)
    ask=max(0.0,_finite_number(row.get("ask")) or 0.0)
    last=max(0.0,_finite_number(row.get("last")) or 0.0)
    if bid>0 and ask>0:return (bid+ask)/2.0,"bid_ask_mid",bid,ask,last
    if last>0:return last,"last",bid,ask,last
    if bid>0 or ask>0:return max(bid,ask),"one_sided_quote",bid,ask,last
    return 0.0,"unavailable",bid,ask,last

def execute_options_snapshot(v:dict,root:Path,input_root:Path|None,artifact_root:Path|None,scanner_cls:Any)->dict:
    if input_root is None:raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE requires governed input_root")
    if artifact_root is None:raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE requires receipt_dir artifact storage")
    args=v["arguments"];descriptor=resolve_dataset(input_root,"options_snapshot",args["dataset"])
    try:payload=json.loads(descriptor["path"].read_text(encoding="utf-8"))
    except Exception as e:raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE dataset must be valid JSON") from e
    meta={}
    if isinstance(payload,dict):
        rows=payload.get("rows")
        meta={
            "capture_source":str(payload.get("capture_source") or payload.get("source") or "").strip() or None,
            "captured_at":str(payload.get("captured_at") or payload.get("ts") or "").strip() or None,
        }
    else:rows=payload
    if not isinstance(rows,list):raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE dataset must be a JSON list or object containing rows list")
    state=args["snapshot_state"]
    if state in {"watch-only-no-history","no-snapshot"} and rows:
        raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE snapshot_state contradicts non-empty dataset")
    if not rows and state in {"current-live","watch-only-last-known"} and not args["empty_reason"]:
        raise CanonicalDispatchError("OPTIONS_SNAPSHOT_ANALYZE empty_reason is required for empty available-state snapshot")
    bounded=rows[:args["max_rows"]]
    as_of=datetime.fromisoformat(args["as_of_utc"].replace("Z","+00:00")).astimezone(timezone.utc)
    analyzed=[];reason_counts={};calc_iv_values=[];total_notional=0.0;calls=0;puts=0
    for index,raw in enumerate(bounded):
        if not isinstance(raw,dict):
            reason="row_not_object";reason_counts[reason]=reason_counts.get(reason,0)+1
            analyzed.append({"row_index":index,"status":"unavailable","reason":reason,"reasons":[reason]});continue
        symbol=str(raw.get("symbol") or "").strip().upper()
        expiry_dt,expiry_iso,expiry_basis=_options_expiry_utc(raw)
        strike=_finite_number(raw.get("strike"))
        und=_finite_number(raw.get("undPrice") if raw.get("undPrice") not in (None,"") else raw.get("underlying_price"))
        right_raw=str(raw.get("right") or "").strip().upper()
        right="C" if right_raw in {"C","CALL"} else ("P" if right_raw in {"P","PUT"} else "")
        if right=="C":calls+=1
        elif right=="P":puts+=1
        price,price_basis,bid,ask,last=_options_quote_basis(raw)
        try:volume=max(0,int(float(raw.get("volume") or 0)))
        except Exception:volume=0
        notional=round(price*100.0*max(1,volume),2) if price>0 else 0.0
        total_notional+=notional
        reasons=[]
        if not symbol or not _SYMBOL.fullmatch(symbol):reasons.append("symbol_invalid")
        if expiry_dt is None:reasons.append(expiry_basis or "expiry_invalid")
        if strike is None or strike<=0:reasons.append("strike_unavailable")
        if not right:reasons.append("right_invalid")
        if und is None or und<=0:reasons.append("underlying_price_unavailable")
        if price<=0:reasons.append("option_price_unavailable")
        t_years=None
        if expiry_dt is not None:
            seconds=(expiry_dt-as_of).total_seconds()
            if seconds<=0:reasons.append("expired_at_as_of")
            else:t_years=seconds/(365.0*24.0*3600.0)
        calc_iv=None;greeks={}
        if not reasons and t_years is not None:
            calc_iv=scanner_cls._implied_vol(price,float(und),float(strike),t_years,args["risk_free_rate"],right)
            if calc_iv is None or calc_iv<=0:reasons.append("implied_vol_unavailable")
            else:
                _,greeks=scanner_cls._bs_price_greeks(float(und),float(strike),t_years,args["risk_free_rate"],float(calc_iv),right)
                if not isinstance(greeks,dict) or not greeks:reasons.append("greeks_unavailable")
                else:calc_iv_values.append(float(calc_iv))
        ib_fields={}
        for key in ("ib_model_price","ib_iv","ib_delta","ib_gamma","ib_vega","ib_theta"):
            value=_finite_number(raw.get(key))
            if value is not None:ib_fields[key]=value
        comparison={}
        for calc_key,ib_key in (
            ("calc_iv","ib_iv"),("calc_delta","ib_delta"),("calc_gamma","ib_gamma"),
            ("calc_vega","ib_vega"),("calc_theta","ib_theta"),
        ):
            calc_value=float(calc_iv) if calc_key=="calc_iv" and calc_iv is not None else _finite_number(greeks.get(calc_key.removeprefix("calc_")))
            ib_value=ib_fields.get(ib_key)
            if calc_value is not None and ib_value is not None:comparison[f"{calc_key}_minus_{ib_key}"]=calc_value-ib_value
        status="analyzed" if not reasons else "unavailable"
        for reason in reasons:reason_counts[reason]=reason_counts.get(reason,0)+1
        analyzed.append({
            "row_index":index,"symbol":symbol or None,
            "expiry":str(raw.get("expiry") or raw.get("lastTradeDateOrContractMonth") or "") or None,
            "expiry_utc":expiry_iso or None,"expiry_time_basis":expiry_basis or None,
            "strike":strike,"right":right or None,
            "bid":bid,"ask":ask,"last":last,"price_basis":price_basis,"analysis_price":price,
            "volume":volume,"notional_usd":notional,"underlying_price":und,
            "as_of_utc":args["as_of_utc"],"time_to_expiry_years":t_years,
            "moneyness_pct":round(((float(strike)/float(und))-1.0)*100.0,6) if strike and und and und>0 else None,
            **ib_fields,"calc_iv":float(calc_iv) if calc_iv is not None else None,
            "calc_delta":_finite_number(greeks.get("delta")),"calc_gamma":_finite_number(greeks.get("gamma")),
            "calc_vega":_finite_number(greeks.get("vega")),"calc_theta":_finite_number(greeks.get("theta")),
            "comparison":comparison,"status":status,"reason":reasons[0] if reasons else None,"reasons":reasons,
        })
    analyzed_count=sum(1 for row in analyzed if row.get("status")=="analyzed")
    summary={
        "snapshot_state":state,"empty_reason":args["empty_reason"] or None,
        "input_row_count":len(rows),"bounded_row_count":len(bounded),"analyzed_row_count":analyzed_count,
        "unavailable_row_count":len(analyzed)-analyzed_count,"call_rows":calls,"put_rows":puts,
        "total_notional_usd":round(total_notional,2),
        "average_calc_iv":(sum(calc_iv_values)/len(calc_iv_values)) if calc_iv_values else None,
        "reason_counts":reason_counts,"capture_source":meta.get("capture_source"),"captured_at":meta.get("captured_at"),
    }
    evidence_root=(artifact_root/"options_snapshot").resolve();evidence_root.mkdir(parents=True,exist_ok=True)
    rows_path=evidence_root/"analytics.json";summary_path=evidence_root/"summary.json"
    rows_path.write_text(json.dumps(analyzed,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False,default=str)+"\n",encoding="utf-8")
    summary_path.write_text(json.dumps(summary,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False,default=str)+"\n",encoding="utf-8")
    artifacts=[artifact_descriptor(rows_path,artifact_root),artifact_descriptor(summary_path,artifact_root)]
    return {
        "schema":"mmibkr.options_snapshot_analysis.v1",
        "dataset":{k:descriptor[k] for k in ("relative_path","sha256","bytes")},
        "as_of_utc":args["as_of_utc"],"risk_free_rate":args["risk_free_rate"],
        "snapshot_state":state,"empty_reason":args["empty_reason"] or None,"summary":summary,
        "row_sample":deepcopy(analyzed[:50]),"analytics_sha256":sha(analyzed),"artifacts":artifacts,
        "canonical_dependencies":options_snapshot_dependencies(root),
        "policy":{
            "snapshot_input_only":True,"deterministic_as_of":True,"ibkr_acquisition":False,
            "alpaca_acquisition":False,"network_acquisition":False,
            "expiry_without_exact_time":"end_of_utc_day_assumption",
        },
        "safety":{
            "research_only":True,"broker_submit":False,"broker_cancel":False,"broker_flatten":False,
            "strategy_spec_write":False,"runtime_activation":False,"promotion_mutation":False,"live_trading":False,
        },
    }


def news_feature_sidecar_dependencies(root:Path)->dict[str,str]:
    return {
        "scripts/operator/news_theme_weight_review_probe_14nh.py":private_blob_identity(root,"scripts/operator/news_theme_weight_review_probe_14nh.py"),
        "scripts/operator/news_feature_sidecar_probe_14ni.py":private_blob_identity(root,"scripts/operator/news_feature_sidecar_probe_14ni.py"),
    }

def _news_count_map_add(node:dict[str,int],key:Any)->None:
    text=str(key or "").strip()
    if text:node[text]=int(node.get(text,0))+1

def _news_feature_evidence_rows(articles:list[dict],split_fn:Any,policy_fn:Any)->tuple[list[dict],dict]:
    by_symbol={}
    for row in articles:
        if not isinstance(row,dict):continue
        symbol=str(row.get("symbol") or "").strip().upper()
        if not symbol:continue
        node=by_symbol.setdefault(symbol,{"method_counts":{},"source_types":{},"providers":{},"titles":[]})
        _news_count_map_add(node["method_counts"],row.get("match_method"))
        _news_count_map_add(node["source_types"],row.get("source_type"))
        _news_count_map_add(node["providers"],row.get("provider"))
        title=str(row.get("title") or "").strip()
        if title and title not in node["titles"] and len(node["titles"])<3:node["titles"].append(title[:180])
    evidence=[];symbol_policies={}
    for symbol,node in sorted(by_symbol.items()):
        split=split_fn(node["method_counts"])
        matched=sum(int(v or 0) for v in node["method_counts"].values())
        direct=int(split.get("direct_count") or 0);alias=int(split.get("alias_count") or 0)
        theme=int(split.get("theme_count") or 0);macro=int(split.get("macro_count") or 0);other=int(split.get("other_count") or 0)
        policy,reason,theme_only,direct_required=policy_fn(matched,direct,alias,theme,macro,other)
        row={
            "symbol":symbol,"matched_articles":matched,"direct_articles":direct,"alias_articles":alias,
            "theme_articles":theme,"macro_articles":macro,"other_articles":other,
            "theme_counts":json.dumps(split.get("theme_counts") or {},sort_keys=True),
            "method_counts":json.dumps(node["method_counts"],sort_keys=True),
            "source_types":json.dumps(node["source_types"],sort_keys=True),
            "providers":json.dumps(node["providers"],sort_keys=True),
            "weighted_evidence":float(split.get("weighted_evidence") or 0.0),
            "theme_only_flag":bool(theme_only),"direct_required_flag":bool(direct_required),
            "policy":policy,"reason":reason,"example_titles":" | ".join(node["titles"]),
        }
        evidence.append(row)
        symbol_policies[symbol]={
            "policy":policy,
            "direct_required_for_trade_signal":bool(direct_required),
            "theme_only_flag":bool(theme_only),
            "recommended_feature_behavior":(
                "do_not_use_theme_only_as_trade_signal" if theme_only else
                "use_direct_alias_score_with_low_weight_theme_overlay" if direct+alias>0 and theme>0 else
                "use_direct_alias_score" if direct+alias>0 else
                "context_only"
            ),
            "method_counts":deepcopy(node["method_counts"]),
            "theme_counts":deepcopy(split.get("theme_counts") or {}),
        }
    return evidence,symbol_policies

def execute_news_feature_sidecar(v:dict,root:Path,input_root:Path|None,receipt_dir:Path|None,artifact_root:Path|None,score_fn:Any)->dict:
    if artifact_root is None or receipt_dir is None:
        raise CanonicalDispatchError("NEWS_FEATURE_SIDECAR_BUILD requires receipt_dir artifact storage")
    args=v["arguments"]
    resolved=resolve_artifact_ref(input_root,receipt_dir,args["articles"],"NEWS_FEATURE_SIDECAR_BUILD articles")
    try:articles=json.loads(resolved["path"].read_text(encoding="utf-8"))
    except Exception as e:raise CanonicalDispatchError("NEWS_FEATURE_SIDECAR_BUILD articles must be valid JSON") from e
    if not isinstance(articles,list):raise CanonicalDispatchError("NEWS_FEATURE_SIDECAR_BUILD articles must be a JSON list")
    if len(articles)>args["max_article_rows"]:raise CanonicalDispatchError("NEWS_FEATURE_SIDECAR_BUILD article row bound exceeded")
    split_fn=private_callable(root,"scripts/operator/news_theme_weight_review_probe_14nh.py","scripts.operator.news_theme_weight_review_probe_14nh","_split_method_counts")
    policy_fn=private_callable(root,"scripts/operator/news_theme_weight_review_probe_14nh.py","scripts.operator.news_theme_weight_review_probe_14nh","_policy_for_symbol")
    contract_fn=private_callable(root,"scripts/operator/news_feature_sidecar_probe_14ni.py","scripts.operator.news_feature_sidecar_probe_14ni","_build_contract")
    policy_module=sys.modules.get(getattr(split_fn,"__module__",""))
    weights=deepcopy(getattr(policy_module,"DEFAULT_METHOD_WEIGHTS",{}))
    if not isinstance(weights,dict) or not weights:raise CanonicalDispatchError("canonical News policy weights are unavailable")
    evidence,symbol_policies=_news_feature_evidence_rows(articles,split_fn,policy_fn)
    policy_stub={
        "schema_version":"news_feature_policy_stub_14nh.v1",
        "review_only":True,
        "do_not_apply_blindly":True,
        "default_method_weights":weights,
        "default_theme_policy":"context_only_until_direct_or_alias_evidence",
        "symbol_policies":symbol_policies,
    }
    feature_rows=[score_fn(row,policy_stub,args["feature_asof_utc"],args["source_run_id"]) for row in evidence]
    feature_rows=[row for row in feature_rows if isinstance(row,dict) and row.get("SYMBOL")]
    feature_rows.sort(key=lambda r:(-float(r.get("NEWS_COMPOSITE_SCORE_24H") or 0),-float(r.get("NEWS_MACRO_CONTEXT_SCORE_24H") or 0),str(r.get("SYMBOL") or "")))
    contract=contract_fn(policy_stub,args["feature_window_hours"])
    if not isinstance(contract,dict) or contract.get("primary_key")!=["FEATURE_ASOF_UTC","SOURCE_RUN_ID","SYMBOL"]:
        raise CanonicalDispatchError("canonical News feature contract rejected")
    time_semantics=contract.get("time_semantics") or {}
    if "FEATURE_ASOF_UTC" not in str(time_semantics.get("no_lookahead_rule") or ""):
        raise CanonicalDispatchError("canonical News no-lookahead rule rejected")
    trade_signal=[row for row in feature_rows if float(row.get("NEWS_COMPOSITE_SCORE_24H") or 0)>0 and not bool(row.get("NEWS_DIRECT_REQUIRED_FLAG"))]
    context_only=[row for row in feature_rows if bool(row.get("NEWS_DIRECT_REQUIRED_FLAG")) or bool(row.get("NEWS_THEME_ONLY_FLAG"))]
    evidence_root=(artifact_root/"news_feature_sidecar").resolve();evidence_root.mkdir(parents=True,exist_ok=True)
    payloads={
        "news_feature_sidecar.json":feature_rows,
        "policy_evidence.json":evidence,
        "feature_policy_stub.json":policy_stub,
        "feature_column_contract.json":contract,
        "no_lookahead_audit.json":{
            "schema":"mmibkr.news_feature_no_lookahead_audit.v1",
            "source_run_id":args["source_run_id"],
            "feature_asof_utc":args["feature_asof_utc"],
            "rule":"FEATURE_ASOF_UTC <= bar_timestamp",
            "price_bars_read":False,"labels_read":False,"fills_read":False,"pnl_read":False,
            "backtest_outcomes_read":False,"broker_state_read":False,
        },
    }
    artifacts=[];artifact_map={}
    for name,node in payloads.items():
        target=evidence_root/name
        target.write_text(json.dumps(node,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False,default=str)+"\n",encoding="utf-8")
        desc=artifact_descriptor(target,artifact_root);artifacts.append(desc);artifact_map[name]=desc
    csv_target=evidence_root/"news_feature_sidecar.csv"
    fieldnames=list(getattr(sys.modules.get(getattr(score_fn,"__module__","")),"FEATURE_COLUMNS",[]))
    if not fieldnames and feature_rows:fieldnames=list(feature_rows[0])
    with csv_target.open("w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=fieldnames,extrasaction="ignore");writer.writeheader()
        for row in feature_rows:writer.writerow(row)
    csv_desc=artifact_descriptor(csv_target,artifact_root);artifacts.append(csv_desc);artifact_map["news_feature_sidecar.csv"]=csv_desc
    source_ref={k:resolved[k] for k in ("scope","relative_path","sha256","bytes")}
    if resolved.get("job_fingerprint") is not None:source_ref["job_fingerprint"]=resolved["job_fingerprint"]
    return {
        "schema":"mmibkr.news_feature_sidecar.v1",
        "source_articles":source_ref,
        "source_run_id":args["source_run_id"],
        "feature_asof_utc":args["feature_asof_utc"],
        "feature_window_hours":args["feature_window_hours"],
        "article_row_count":len(articles),
        "feature_row_count":len(feature_rows),
        "trade_signal_eligible_rows":len(trade_signal),
        "context_only_rows":len(context_only),
        "theme_only_rows":sum(1 for row in feature_rows if bool(row.get("NEWS_THEME_ONLY_FLAG"))),
        "direct_required_rows":sum(1 for row in feature_rows if bool(row.get("NEWS_DIRECT_REQUIRED_FLAG"))),
        "feature_rows_sha256":sha(feature_rows),
        "policy_evidence_sha256":sha(evidence),
        "feature_row_sample":deepcopy(feature_rows[:25]),
        "feature_contract":sanitize_public_tree(contract),
        "artifacts":artifacts,"artifact_map":artifact_map,
        "canonical_dependencies":news_feature_sidecar_dependencies(root),
        "no_lookahead":{
            "rule":"FEATURE_ASOF_UTC <= bar_timestamp",
            "price_bars_read":False,"labels_read":False,"fills_read":False,"pnl_read":False,
            "backtest_outcomes_read":False,"broker_state_read":False,
        },
        "safety":{
            "research_only":True,"provider_acquisition":False,"network_acquisition":False,
            "strategy_spec_write":False,"runtime_activation":False,"promotion_mutation":False,
            "broker_submit":False,"broker_cancel":False,"broker_flatten":False,"live_trading":False,
        },
    }

def execute_valid(v:dict,root:Path,input_root:Path|None=None,artifact_root:Path|None=None,receipt_dir:Path|None=None)->dict:
    fn=None if v["capability_id"] in {"CANONICAL_DATA_MATERIALIZE","FEATURE_CONTRACT_VALIDATE","STRATEGY_PREVIEW"} else load_callable(root,CAPABILITIES[v["capability_id"]])
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
        result=sanitize_crw_result(raw,v["arguments"],root=root,artifact_root=artifact_root)
    elif v["capability_id"]=="AUTOTUNER_CAMPAIGN":
        if input_root is None:raise CanonicalDispatchError("AUTOTUNER_CAMPAIGN requires governed input_root")
        args=v["arguments"]; descriptor=resolve_dataset(input_root,"autotuner",args["dataset"])
        normalized=normalized_crw_spec(root,args["strategy_spec"])
        state=deepcopy(args["state"])
        if state is None:
            new_state=private_callable(root,"autotuner_campaign_planner.py","autotuner_campaign_planner","new_campaign_state")
            state=new_state(normalized["strategy_spec_digest"])
        history=deepcopy(args["history"])
        if history is None:
            history={"schema":"mm.autotuner_campaign_history.v1","strategy_spec_digest":normalized["strategy_spec_digest"],"results":[]}
        report,next_state,next_history=fn(
            strategy_payload=deepcopy(args["strategy_spec"]),data_root=descriptor["path"].parent,
            state=state,history=history,tune_parameters=args["tune_parameters"],
            advisory_suggestions=args["advisory_suggestions"],batch_size=args["batch_size"],
            coarse_points=args["coarse_points"],score_tolerance_fraction=args["score_tolerance_fraction"],
            backtest_runner=governed_autotuner_backtest_runner(root,descriptor["path"],args["strategy_spec"]),
        )
        if not isinstance(report,dict) or report.get("schema")!="mm.autotuner_campaign_iteration.v1":
            raise CanonicalDispatchError("canonical AutoTuner campaign returned invalid contract")
        decision=report.get("decision") or {}; safety=report.get("safety") or {}
        for key,value in {"automatic_promotion":False,"automatic_strategy_spec_write":False}.items():
            if decision.get(key) is not value:raise CanonicalDispatchError(f"AutoTuner campaign authority rejected: {key}")
        for key,value in {"runtime_activation":False,"broker_submit":False,"live_unlock":False}.items():
            if safety.get(key) is not value:raise CanonicalDispatchError(f"AutoTuner campaign safety rejected: {key}")
        result={
            "strategy_spec_digest":normalized["strategy_spec_digest"],
            "dataset":{k:descriptor[k] for k in ("relative_path","sha256","bytes")},
            "report":sanitize_public_tree(report),
            "next_state":sanitize_public_tree(next_state),
            "next_history":sanitize_public_tree(next_history),
            "canonical_dependencies":autotuner_campaign_dependencies(root),
        }
    elif v["capability_id"]=="AUTOTUNER_PRIMARY_VALIDATION":
        if input_root is None:raise CanonicalDispatchError("AUTOTUNER_PRIMARY_VALIDATION requires governed input_root")
        args=v["arguments"]; descriptor=resolve_dataset(input_root,"autotuner",args["dataset"])
        raw=fn(
            deepcopy(args["staged_plan"]),deepcopy(args["strategy_spec"]),descriptor["path"],
            split_policy=deepcopy(args["split_policy"]),
        )
        if not isinstance(raw,dict) or raw.get("schema")!="mm.autotuner_primary_validation_execution.v1" or raw.get("state")!="PRIMARY_VALIDATION_EXECUTED":
            raise CanonicalDispatchError("canonical AutoTuner primary validation returned invalid contract")
        for key in ("automatic_promotion","automatic_strategy_spec_write","runtime_activation","broker_submit"):
            if raw.get(key) is not False:raise CanonicalDispatchError(f"AutoTuner validation authority rejected: {key}")
        trades=raw.get("validation_trade_results") or []
        if not isinstance(trades,list):raise CanonicalDispatchError("AutoTuner validation trade results are invalid")
        public=sanitize_public_tree({k:value for k,value in raw.items() if k!="validation_trade_results"})
        public["validation_trade_result_count"]=len(trades)
        public["validation_trade_results_sha256"]=sha(trades)
        public["dataset"]={k:descriptor[k] for k in ("relative_path","sha256","bytes")}
        public["canonical_dependencies"]=autotuner_validation_dependencies(root)
        result=public
    elif v["capability_id"]=="MODEL_LAB_FIRST_CONSUMER":
        if input_root is None:raise CanonicalDispatchError("MODEL_LAB_FIRST_CONSUMER requires governed input_root")
        result=execute_model_lab_first_consumer(v,root,input_root,fn)
    elif v["capability_id"]=="MODEL_LAB_COMPARE_VALIDATE":
        if input_root is None:raise CanonicalDispatchError("MODEL_LAB_COMPARE_VALIDATE requires governed input_root")
        result=execute_model_lab_compare_validate(v,root,input_root,fn)
    elif v["capability_id"]=="NEWS_REPLAY_ANALYZE":
        result=execute_news_replay(v,root,input_root,artifact_root,fn)
    elif v["capability_id"]=="OPTIONS_SNAPSHOT_ANALYZE":
        result=execute_options_snapshot(v,root,input_root,artifact_root,fn)
    elif v["capability_id"]=="NEWS_FEATURE_SIDECAR_BUILD":
        result=execute_news_feature_sidecar(v,root,input_root,receipt_dir,artifact_root,fn)
    elif v["capability_id"]=="CANONICAL_DATA_MATERIALIZE":
        result=materialize_stock_data(v,root,input_root,artifact_root)
    elif v["capability_id"]=="FEATURE_CONTRACT_VALIDATE":
        result=validate_feature_contract(v,root,input_root,receipt_dir)
    elif v["capability_id"]=="STRATEGY_PREVIEW":
        result=execute_strategy_preview(v,root,input_root,receipt_dir)
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
    else:
        raise CanonicalDispatchError(f"capability executor is not implemented: {v['capability_id']}")
    rb=cbytes(result)
    if len(rb)>v["resources"]["max_output_bytes"]:raise CanonicalDispatchError("canonical result exceeded max_output_bytes")
    fp=sha(v)
    return {"schema":RECEIPT_SCHEMA,"job_id":v["job_id"],"job_fingerprint":fp,"capability_id":v["capability_id"],"status":"completed","authority":{"research_only":True,**FORBIDDEN_AUTHORITY_ASSERTIONS},"mmibkr":v["mmibkr"],"entrypoint":v["entrypoint"],"resources":v["resources"],"result_sha256":hashlib.sha256(rb).hexdigest(),"result":result}

def safe_execute_valid(v:dict,root:Path,input_root:Path|None=None,artifact_root:Path|None=None,receipt_dir:Path|None=None)->dict:
    try:
        return execute_valid(v,root,input_root=input_root,artifact_root=artifact_root,receipt_dir=receipt_dir)
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

def validate_cached_artifacts(receipt:dict,receipt_dir:Path,fp:str)->None:
    result=receipt.get("result") or {}; artifacts=result.get("artifacts")
    if receipt.get("capability_id")=="CANONICAL_DATA_MATERIALIZE" and (not isinstance(artifacts,list) or not artifacts):
        raise CanonicalDispatchError("cached materialization receipt has no artifacts")
    if not artifacts:return
    if not isinstance(artifacts,list):raise CanonicalDispatchError("cached artifact descriptor list invalid")
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
    rd=receipt_dir.resolve() if receipt_dir is not None else None
    v=validate_request(req,source_root,source_receipt,input_root=input_root,receipt_dir=rd); fp=sha(v)
    if rd is None:
        if v["capability_id"] in {"CANONICAL_DATA_MATERIALIZE","NEWS_REPLAY_ANALYZE","OPTIONS_SNAPSHOT_ANALYZE","NEWS_FEATURE_SIDECAR_BUILD"}:
            raise CanonicalDispatchError(f"{v['capability_id']} requires receipt_dir artifact storage")
        return {"receipt":safe_execute_valid(v,source_root,input_root=input_root,receipt_dir=None),"cache_hit":False}
    rp=rd/"receipts"/f"{fp}.json"; hit=cached(rp,fp)
    if hit:
        validate_cached_artifacts(hit,rd,fp)
        return {"receipt":hit,"cache_hit":True}
    cp=rd/"claims"/f"{fp}.claim"
    token,hit=acquire_claim(cp,v,fp,rp)
    if hit:
        validate_cached_artifacts(hit,rd,fp)
        return {"receipt":hit,"cache_hit":True}
    stop,lost,thread=start_claim_heartbeat(cp,token,fp)
    published=False
    artifact_root=(rd/"artifacts"/fp).resolve() if v["capability_id"] in {"CANONICAL_DATA_MATERIALIZE","CRW_BACKTEST","NEWS_REPLAY_ANALYZE","OPTIONS_SNAPSHOT_ANALYZE","NEWS_FEATURE_SIDECAR_BUILD"} else None
    if artifact_root is not None:
        shutil.rmtree(artifact_root,ignore_errors=True);artifact_root.mkdir(parents=True,exist_ok=True)
    try:
        r=safe_execute_valid(v,source_root,input_root=input_root,artifact_root=artifact_root,receipt_dir=rd)
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
