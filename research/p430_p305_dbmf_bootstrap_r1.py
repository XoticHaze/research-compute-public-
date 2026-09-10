from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['SPMO','IJS','SPY','IJR','DBMF','BIL','SRLN','HYG','SHY']
START='2015-01-01'; END='2026-09-11'; ADMIT_START='2019-05-31'; ADMIT_END='2026-08-31'
LB=24; EP=.0025; BLOCK=6; NBOOT=5000; SEED=430
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True); OUT=ART/'p430_p305_dbmf_bootstrap_r1.json'
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None)
p305=.5*(r.SPMO+r.IJS); p305ctl=.5*(r.SPY+r.IJR)
bs=[]
for i in range(len(r)):
    w=r[['HYG','SHY','SRLN']].iloc[max(0,i-LB):i].dropna()
    if len(w)<LB: bs.append((np.nan,np.nan)); continue
    b=np.linalg.lstsq(w[['HYG','SHY']].values,w.SRLN.values,rcond=None)[0]
    b=np.clip(b,0,1)
    if b.sum()>1:b=b/b.sum()
    bs.append(tuple(map(float,b)))
b=pd.DataFrame(bs,index=r.index,columns=['hyg','shy']).shift(1)
loanctl=b.hyg*r.HYG+b.shy*r.SHY
q=pd.DataFrame({'challenger':.5*p305+.5*r.DBMF,'matched_control':.5*p305ctl+.5*r.BIL,'core':.5*p305+.5*r.SRLN,'core_control':.5*p305ctl+.5*loanctl}).dropna()
q=q.loc[ADMIT_START:ADMIT_END]
if len(q)!=88 or q.index.min().strftime('%Y-%m-%d')!=ADMIT_START or q.index.max().strftime('%Y-%m-%d')!=ADMIT_END:
    raise SystemExit(f'ADMITTED_SAMPLE_IDENTITY_MISMATCH n={len(q)} start={q.index.min()} end={q.index.max()}')

def cagr(x):
    y=np.asarray(x,dtype=float).copy(); y[0]-=EP; y[-1]-=EP
    return float(np.prod(1+y)**(12/len(y))-1)
def sample_idx(rng,n):
    idx=[]
    while len(idx)<n:
        start=int(rng.integers(0,n-BLOCK+1)); idx.extend(range(start,start+BLOCK))
    return np.array(idx[:n])
actual={'matched_excess':cagr(q.challenger)-cagr(q.matched_control),'core_advantage':cagr(q.challenger)-cagr(q.core),'challenger_cagr':cagr(q.challenger),'control_cagr':cagr(q.matched_control),'core_cagr':cagr(q.core)}
rng=np.random.default_rng(SEED); mex=[]; cadv=[]
arr=q.to_numpy(); n=len(q)
for _ in range(NBOOT):
    ix=sample_idx(rng,n); z=arr[ix]
    mex.append(cagr(z[:,0])-cagr(z[:,1])); cadv.append(cagr(z[:,0])-cagr(z[:,2]))
mex=np.array(mex); cadv=np.array(cadv)
def dist(a):return {'p_nonpositive':float(np.mean(a<=0)),'p05':float(np.quantile(a,.05)),'median':float(np.median(a)),'p95':float(np.quantile(a,.95))}
md=dist(mex); cd=dist(cadv)
passed=md['p_nonpositive']<=.10 and md['p05']>0 and cd['p_nonpositive']<=.20
out={'schema':'research.p430_p305_dbmf_bootstrap_r1.v1','workload_id':'P430_P305_DBMF_BOOTSTRAP_R1','parent':'P305_DBMF_COMPLEMENTARITY','claim':'On the exact 88-month sample admitted by P423 before performance inspection, a fixed paired six-month moving-block bootstrap should show the P305+DBMF matched edge is unlikely to be nonpositive and that its observed advantage over the frozen P249/P373 core is not a single-sequence artifact.','sample_identity':{'start':ADMIT_START,'end':ADMIT_END,'months':88},'bootstrap_contract':{'moving_block_months':BLOCK,'replicates':NBOOT,'seed':SEED,'paired_resampling':True,'endpoint_cost_bps_each':25,'parameter_search':False},'actual':actual,'matched_excess_bootstrap':md,'core_advantage_bootstrap':cd,'decision_rule':'SUPPORTED only if p(nonpositive matched excess)<=10%, the 5th percentile matched excess is >0, and p(nonpositive CAGR advantage versus frozen core)<=20%. No block-length, sample, cost, or threshold rescue after observation.','decision':'P305_DBMF_STATISTICAL_ROBUSTNESS_SUPPORTED' if passed else 'P305_DBMF_STATISTICAL_ROBUSTNESS_NOT_SUPPORTED','scientific_consequence':('Strengthen coverage-valid P305+DBMF scientific utility with paired dependence-aware resampling; Coordinator retains ranking/allocation authority.' if passed else 'Record the failed statistical robustness dimension without erasing P423 chronology and coverage-valid evidence. Do not change block length, sample, weights, costs, or thresholds to rescue; rotate to an independent parent.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'actual_matched_excess_pp':round(100*actual['matched_excess'],3),'actual_core_advantage_pp':round(100*actual['core_advantage'],3),'matched_p_nonpositive':md['p_nonpositive'],'matched_p05_pp':round(100*md['p05'],3),'core_advantage_p_nonpositive':cd['p_nonpositive'],'core_advantage_p05_pp':round(100*cd['p05'],3)},sort_keys=True))
