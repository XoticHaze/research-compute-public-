from __future__ import annotations

"""R3: R2 opportunity selector plus frozen P09 multihorizon adverse-risk gate.

R2's same-step/same-regime CC75 opportunity matcher is unchanged. R3 only withholds
an otherwise-qualified reserve release when the latest fully prior daily P09
multihorizon score is at/above the frozen prior-history 80th percentile for that
calendar year. All capital/economic gates remain unchanged. Research evidence only.
"""

import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

EXPECTED_SCHEMA="mnq-dca-reserve-release-r3-p09-envelope-v1"
EXPECTED_HARNESS="mnq-dca-reserve-release-r3-p09-v1"
EXPECTED_PAYLOAD_SCHEMA="mnq-dca-reserve-release-state-r2-compact-private-payload-v1"
EXPECTED_SOURCES={
 "lifecycle":{"repo":"XoticHaze/mm-IBKR","artifact_id":9914932522,"archive_sha256":"9919084af1b6f0f2429f74acbc5972e719020189964cbecf374262e144a49e23"},
 "replay":{"repo":"XoticHaze/research-foundry","artifact_id":9881343496,"archive_sha256":"9cc2b62b864bab02fe7132eaae9b008aedd18e976152c3f2aa445c5bed6e4362"},
}
EXPECTED_PARITY={"canonical_trades":56,"canonical_dca_events":42,"exact_gross_trades":56,"mtm_within_0_25_points_trades":55}
FEATURES=["return_5","return_20","return_60","volatility_20","distance_ma20","distance_ma60"]
K=8; MIN_POSITIVE=5; FIXED_BUDGET_CONTRACTS=4; P09_Q=0.80
P09_START="2019-05-06"; P09_END="2026-02-20"


def pct_rank(s: pd.Series,w:int=252)->pd.Series:
    def f(a):
        if len(a)<40 or not np.isfinite(a[-1]): return np.nan
        b=a[np.isfinite(a)]
        return np.mean(b<=a[-1]) if len(b) else np.nan
    return s.rolling(w,min_periods=40).apply(f,raw=True)


def p09_state()->tuple[pd.DataFrame,str]:
    x=yf.download("MNQ=F",start=P09_START,end=P09_END,auto_adjust=False,progress=False,threads=False)
    if isinstance(x.columns,pd.MultiIndex): x.columns=x.columns.get_level_values(0)
    x=x.rename(columns=str.lower).dropna(subset=["open","high","low","close"])
    x.index=pd.to_datetime(x.index,utc=True)
    r=x.close.pct_change(); vol5=r.rolling(5).std(); vol20=r.rolling(20).std()
    mom20=x.close.pct_change(20); dd20=x.close/x.close.rolling(20).max()-1
    multi=(pct_rank(vol5)+pct_rank(vol20)+pct_rank(-mom20)+pct_rank(-dd20))/4.0
    d=pd.DataFrame({"multi":multi}).dropna()
    digest=hashlib.sha256(d.to_csv(index=True,float_format="%.17g").encode()).hexdigest()
    return d,digest


def evaluate(payload:dict)->dict:
    required={"schema","source_artifacts","packager_parity","feature_contract","trades","events"}
    if set(payload)!=required or payload["schema"]!=EXPECTED_PAYLOAD_SCHEMA: raise RuntimeError("R3 payload identity mismatch")
    if payload["source_artifacts"]!=EXPECTED_SOURCES or payload["packager_parity"]!=EXPECTED_PARITY: raise RuntimeError("R3 provenance/parity mismatch")
    if payload["feature_contract"].get("features")!=FEATURES: raise RuntimeError("R3 CC75 feature contract mismatch")
    trades=pd.DataFrame(payload["trades"]); events=pd.DataFrame(payload["events"])
    if len(trades)!=56 or len(events)!=42: raise RuntimeError("R3 canonical population mismatch")
    trades["entry"]=pd.to_datetime(trades.entry_fill_timestamp,utc=True)
    events["timestamp"]=pd.to_datetime(events.timestamp,utc=True)
    events["state_bar_timestamp"]=pd.to_datetime(events.state_bar_timestamp,utc=True)
    p09,p09_digest=p09_state()
    years=sorted(set(events.timestamp.dt.year.astype(int)))
    thresholds={}
    for y in years:
        hist=p09[p09.index<pd.Timestamp(f"{y}-01-01",tz="UTC")]
        q=float(hist.multi.quantile(P09_Q)) if len(hist) else np.nan
        if not np.isfinite(q): raise RuntimeError(f"R3 P09 threshold unavailable for {y}")
        thresholds[y]=q
    # Bind each event only to a fully prior daily observation: daily UTC date < event UTC date.
    risk=[]
    for row in events.itertuples(index=False):
        cutoff=pd.Timestamp(row.timestamp.date(),tz="UTC")
        prior=p09[p09.index<cutoff]
        if prior.empty: raise RuntimeError("R3 P09 state unavailable")
        score=float(prior.multi.iloc[-1]); threshold=thresholds[int(row.timestamp.year)]
        risk.append((score,threshold,bool(score>=threshold)))
    events["p09_multi"]=[x[0] for x in risk]; events["p09_threshold"]=[x[1] for x in risk]; events["p09_high_risk"]=[x[2] for x in risk]
    events=events.sort_values("timestamp").reset_index(drop=True)

    releases_r2={}; releases_r3={}; first_dca={}; first_eligible=None; eligible_events=0
    for row in events.itertuples(index=False):
        if int(row.step)==1: first_dca[int(row.trade_idx)]=row._asdict()
        prior=events[(events.timestamp<row.timestamp)&(events.step==row.step)&(events.regime==row.regime)]
        if len(prior)<K: continue
        eligible_events+=1
        if first_eligible is None: first_eligible=row.timestamp
        q=np.asarray(row.state_features,dtype=float); scale=np.asarray(row.query_year_scale,dtype=float)
        dist=[]
        for pr in prior.itertuples(index=False):
            p=np.asarray(pr.state_features,dtype=float); dist.append(float(np.sqrt(np.mean(((p-q)/scale)**2))))
        nearest=prior.assign(_distance=dist).nsmallest(K,"_distance")
        qualified=float(nearest.incremental_exit_points.mean())>0 and int(nearest.positive_extra.sum())>=MIN_POSITIVE
        ti=int(row.trade_idx)
        if qualified and ti not in releases_r2:
            releases_r2[ti]=row._asdict()
            if not bool(row.p09_high_risk): releases_r3[ti]=row._asdict()
    if first_eligible is None: raise RuntimeError("R3 no causal evaluation boundary")

    def sim(releases:dict[int,dict])->pd.DataFrame:
        rows=[]
        for tr in trades.itertuples(index=False):
            ti=int(tr.trade_idx); cand=releases.get(ti); always=first_dca.get(ti)
            rows.append({"trade_idx":ti,"entry":tr.entry,"base_gross":float(tr.baseline_gross_contract_points),"base_min":float(tr.baseline_min_mtm_contract_points),"base_qty":int(tr.baseline_final_qty),
             "cand_gross":float(cand["extra_gross_contract_points"]) if cand else float(tr.baseline_gross_contract_points),"cand_min":float(cand["extra_min_mtm_contract_points"]) if cand else float(tr.baseline_min_mtm_contract_points),"cand_qty":int(cand["extra_final_qty"]) if cand else int(tr.baseline_final_qty),
             "always_gross":float(always["extra_gross_contract_points"]) if always else float(tr.baseline_gross_contract_points),"always_min":float(always["extra_min_mtm_contract_points"]) if always else float(tr.baseline_min_mtm_contract_points),"always_qty":int(always["extra_final_qty"]) if always else int(tr.baseline_final_qty),"released":cand is not None})
        return pd.DataFrame(rows)
    evaluation=sim(releases_r3); evaluation=evaluation[evaluation.entry>=first_eligible].sort_values("entry").reset_index(drop=True)
    r2eval=sim(releases_r2); r2eval=r2eval[r2eval.entry>=first_eligible].sort_values("entry").reset_index(drop=True)
    cand_inc=float((evaluation.cand_gross-evaluation.base_gross).sum()); always_inc=float((evaluation.always_gross-evaluation.base_gross).sum())
    cand_dd=float((evaluation.base_min-evaluation.cand_min).mean()); always_dd=float((evaluation.base_min-evaluation.always_min).mean())
    capture=cand_inc/always_inc if always_inc>0 else None; dd_ratio=cand_dd/always_dd if always_dd>0 else None
    folds=[]
    for fold,idx in enumerate(np.array_split(np.arange(len(evaluation)),3),start=1):
        part=evaluation.iloc[idx]
        folds.append({"fold":fold,"trades":int(len(part)),"candidate_incremental_contract_points":float((part.cand_gross-part.base_gross).sum()),"always_release_incremental_contract_points":float((part.always_gross-part.base_gross).sum()),"candidate_mean_added_drawdown_contract_points":float((part.base_min-part.cand_min).mean()),"always_release_mean_added_drawdown_contract_points":float((part.base_min-part.always_min).mean())})
    pos=sum(x["candidate_incremental_contract_points"]>0 for x in folds)
    supported=bool(cand_inc>0 and capture is not None and capture>=.50 and dd_ratio is not None and dd_ratio<=.70 and pos>=2)
    suppressed=sorted(set(releases_r2)-set(releases_r3))
    return {"schema":"public_research.mnq_dca_reserve_release_r3_p09_receipt.v1","research_only":True,"decision":"R3_P09_RISK_GATED_RESERVE_RELEASE_SUPPORTED" if supported else "R3_P09_RISK_GATED_RESERVE_RELEASE_NOT_SUPPORTED",
      "scientific_change":"retain frozen R2 opportunity selector; suppress otherwise-qualified release only when frozen P09 multihorizon risk score is at/above its strictly-prior-history 80th percentile",
      "p09":{"source":"Yahoo Finance MNQ=F","window":[P09_START,P09_END],"data_digest_sha256":p09_digest,"quantile":P09_Q,"thresholds_by_event_year":thresholds,"suppressed_r2_release_trade_indices":suppressed},
      "r2_reference":{"release_trades":int(r2eval.released.sum()),"incremental_contract_points":float((r2eval.cand_gross-r2eval.base_gross).sum()),"capture_of_naive_increment":float((r2eval.cand_gross-r2eval.base_gross).sum()/always_inc),"added_drawdown_ratio_vs_naive":float((r2eval.base_min-r2eval.cand_min).mean()/always_dd)},
      "evaluation":{"start":first_eligible.isoformat(),"trades":int(len(evaluation)),"eligible_dca_events":eligible_events,"candidate_release_trades":int(evaluation.released.sum()),"candidate_incremental_contract_points":cand_inc,"always_release_incremental_contract_points":always_inc,"candidate_capture_of_always_release_increment":capture,"candidate_mean_added_drawdown_contract_points":cand_dd,"always_release_mean_added_drawdown_contract_points":always_dd,"candidate_added_drawdown_ratio_vs_always":dd_ratio,"positive_candidate_increment_folds":pos,"folds":folds},
      "gates":{"capture_min":.50,"added_drawdown_ratio_max":.70,"positive_folds_min":2},"promotion_authority":False,"allocation_authority":False,"runtime_authority":False,"broker_authority":False,"live_trading_change":False}


def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--envelope",required=True,type=Path); p.add_argument("--ciphertext",required=True,type=Path); p.add_argument("--private-key",required=True,type=Path); p.add_argument("--run-id",required=True); p.add_argument("--response-root",required=True); a=p.parse_args()
    env=json.loads(a.envelope.read_text()); plain=decrypt_assembled_ciphertext(envelope=env,ciphertext=a.ciphertext.read_bytes(),private_key_path=a.private_key,expected_schema=EXPECTED_SCHEMA,expected_run_id=a.run_id,expected_harness=EXPECTED_HARNESS,response_root=a.response_root)
    out=evaluate(json.loads(plain)); out["private_payload_sha256"]=hashlib.sha256(plain).hexdigest(); print("MNQ_DCA_RESERVE_RELEASE_R3_P09_RECEIPT="+json.dumps(out,sort_keys=True,allow_nan=False)); return 0
if __name__=="__main__": raise SystemExit(main())
