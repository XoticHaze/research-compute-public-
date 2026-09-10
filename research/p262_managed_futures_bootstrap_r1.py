from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS=['DBMF','BIL']
WINDOWS={'2020':'2020-01-01','2022':'2022-01-01'}
COST_BP=10
BLOCK=12
REPS=5000
SEED=262

raw=yf.download(TICKERS,start='2019-01-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=close[TICKERS].dropna().resample('ME').last().pct_change().dropna()
rng=np.random.default_rng(SEED)
out={}
for name,start in WINDOWS.items():
    q=r.loc[r.index>=pd.Timestamp(start)].copy()
    excess=(q.DBMF-q.BIL).to_numpy(float)
    observed=float(np.prod(1+q.DBMF.to_numpy(float)-np.r_[COST_BP/10000,np.zeros(len(q)-2),COST_BP/10000])**(12/len(q))-1 - (np.prod(1+q.BIL.to_numpy(float)-np.r_[COST_BP/10000,np.zeros(len(q)-2),COST_BP/10000])**(12/len(q))-1))
    starts=np.arange(max(1,len(excess)-BLOCK+1))
    vals=[]
    for _ in range(REPS):
        chunks=[]
        while sum(len(c) for c in chunks)<len(excess):
            s=int(rng.choice(starts)); chunks.append(excess[s:s+BLOCK])
        sample=np.concatenate(chunks)[:len(excess)]
        vals.append(float(sample.mean()*12))
    vals=np.asarray(vals)
    out[name]={'months':int(len(excess)),'observed_cash_excess_cagr':observed,'bootstrap_annualized_excess_median':float(np.median(vals)),'bootstrap_annualized_excess_p05':float(np.quantile(vals,.05)),'bootstrap_annualized_excess_p95':float(np.quantile(vals,.95)),'probability_excess_le_zero':float(np.mean(vals<=0))}
a,b=out['2020'],out['2022']
support=(a['bootstrap_annualized_excess_p05']>0 and b['bootstrap_annualized_excess_p05']>0 and a['probability_excess_le_zero']<0.10 and b['probability_excess_le_zero']<0.10)
res={'schema':'research.p262_managed_futures_bootstrap_r1','parent':'P261/P262','claim':'P261 cash-relative excess persists under a fixed paired 12-month moving-block bootstrap without changing DBMF, BIL, windows, costs, or model parameters.','contract':{'candidate':'DBMF','matched_control':'BIL','windows':WINDOWS,'cost_bps':COST_BP,'block_months':BLOCK,'reps':REPS,'seed':SEED,'gate':'5th percentile annualized paired excess >0 and P(excess<=0)<10% in both windows','no_parameter_window_fund_or_threshold_search':True},'tests':out,'decision':'P262_BOOTSTRAP_SUPPORTED' if support else 'P262_BOOTSTRAP_NOT_SUPPORTED','interpretation_rule':'This adjudicates the P261 chronology-breadth weakness only. Failure narrows confidence but does not erase P261 passing cash-excess/risk/correlation evidence.','boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p262_managed_futures_bootstrap_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
