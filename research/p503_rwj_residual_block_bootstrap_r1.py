from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p503_rwj_residual_block_bootstrap_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
T=['RWJ','IJR','IWN'];START='2010-01-01';HURDLE=.0025;BLOCK=12;B=2000;SEED=503
raw=yf.download(T,start=START,end='2026-09-11',auto_adjust=True,progress=False,threads=False);c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw;m=c[T].resample('ME').last().pct_change(fill_method=None).dropna();y=(m.RWJ-m.IJR).to_numpy();x=(m.IWN-m.IJR).to_numpy();X=np.column_stack([np.ones(len(x)),x]);beta=np.linalg.lstsq(X,y,rcond=None)[0];point=float(beta[0]*12-HURDLE)
rng=np.random.default_rng(SEED);n=len(y);starts=np.arange(0,n-BLOCK+1);vals=[]
for _ in range(B):
 idx=[]
 while len(idx)<n:
  s=int(rng.choice(starts));idx.extend(range(s,s+BLOCK))
 idx=np.array(idx[:n]);bb=np.linalg.lstsq(np.column_stack([np.ones(n),x[idx]]),y[idx],rcond=None)[0];vals.append(float(bb[0]*12-HURDLE))
lo,med,hi=np.quantile(vals,[.025,.5,.975]);prob=float(np.mean(np.array(vals)>0));decision='RWJ_RESIDUAL_95CI_EXCLUDES_ZERO' if lo>0 else 'RWJ_RESIDUAL_ECONOMIC_POINT_ESTIMATE_BUT_95CI_INCLUDES_ZERO'
out={'schema':'research.p503_rwj_residual_block_bootstrap_r1.v1','workload_id':'P503_RWJ_RESIDUAL_BLOCK_BOOTSTRAP_R1','parent':'REVENUE_WEIGHTING_FUND_FAMILY','claim':'Orthogonal uncertainty falsifier for the unchanged P498 residual: monthly RWJ-IJR excess regressed on IWN-IJR, with the same 25 bp annual hurdle. Use deterministic 12-month moving-block bootstrap to preserve local serial dependence; no alternate factors, windows, block-length search, product substitution, or threshold rescue.','contract':{'start':START,'dependent':'RWJ-IJR monthly excess','factor':'IWN-IJR monthly value spread','annual_residual_hurdle_bps':25,'moving_block_months':BLOCK,'bootstrap_draws':B,'seed':SEED,'uncertainty_rule':'95% moving-block bootstrap interval of annualized after-hurdle intercept excludes zero for strong statistical robustness; otherwise retain economic point estimate but classify statistical uncertainty unresolved.'},'months':n,'point_after_hurdle_annual_alpha':point,'bootstrap':{'p2_5':float(lo),'median':float(med),'p97_5':float(hi),'probability_positive':prob},'decision':decision,'scientific_consequence':'This test adjudicates uncertainty only. A CI crossing zero does not erase P497/P498 economic evidence; it prevents escalation to strong statistical-robustness language and redirects future work to genuinely out-of-sample or independent implementation evidence.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':decision,'months':n,'point_pp':round(point*100,3),'ci95_pp':[round(float(lo)*100,3),round(float(hi)*100,3)],'prob_positive':round(prob,3)},sort_keys=True))
