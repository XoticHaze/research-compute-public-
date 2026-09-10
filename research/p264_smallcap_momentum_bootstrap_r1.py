from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS=['XSMO','IJR','IWM']
WINDOWS={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
COST_BP=10
BLOCK=12
REPS=5000
SEED=264

def endpoint_cost(r,bps=COST_BP):
    q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
    if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
    return q

def paired_bootstrap(excess, block=BLOCK, reps=REPS, seed=SEED):
    x=np.asarray(pd.Series(excess,dtype=float).dropna(),dtype=float); n=len(x)
    rng=np.random.default_rng(seed); starts=np.arange(max(1,n-block+1)); vals=np.empty(reps)
    for j in range(reps):
        draw=[]
        while len(draw)<n:
            s=int(rng.choice(starts)); draw.extend(x[s:min(s+block,n)].tolist())
        vals[j]=float(np.mean(draw[:n])*12)
    return {'months':int(n),'median_annualized_excess':float(np.median(vals)),'p05_annualized_excess':float(np.quantile(vals,0.05)),'p95_annualized_excess':float(np.quantile(vals,0.95)),'probability_excess_le_zero':float(np.mean(vals<=0))}

raw=yf.download(TICKERS,start='2014-01-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=close[TICKERS].dropna().resample('ME').last(); ret=m.pct_change().dropna(); out={}
for name,start in WINDOWS.items():
    q=ret.loc[ret.index>=pd.Timestamp(start)].copy()
    cand=endpoint_cost(q.XSMO); ijr=endpoint_cost(q.IJR); iwm=endpoint_cost(q.IWM)
    x1=(cand-ijr).dropna(); x2=(cand-iwm).dropna()
    b1=paired_bootstrap(x1,seed=SEED+int(name)); b2=paired_bootstrap(x2,seed=SEED+int(name)+1)
    out[name]={'observed_annualized_excess_vs_ijr':float(x1.mean()*12),'observed_annualized_excess_vs_iwm':float(x2.mean()*12),'bootstrap_vs_ijr':b1,'bootstrap_vs_iwm':b2}

def gate(z):
    return z['p05_annualized_excess']>0 and z['probability_excess_le_zero']<0.10
support=all(gate(out[w]['bootstrap_vs_ijr']) and gate(out[w]['bootstrap_vs_iwm']) for w in WINDOWS)
res={'schema':'research.p264_smallcap_momentum_bootstrap_r1','parent':'P263/P264','claim':'The fixed XSMO matched excess from P263 survives a serial-dependence-preserving paired moving-block bootstrap against both IJR and IWM without changing funds, windows, costs, or parameters.','contract':{'candidate':'XSMO','matched_controls':['IJR','IWM'],'windows':WINDOWS,'cost_bps':COST_BP,'block_months':BLOCK,'bootstrap_reps':REPS,'seed':SEED,'gate':'for both controls in every predeclared window: p05 annualized excess >0 and P(excess<=0)<10%','no_fund_window_weight_threshold_or_parameter_search':True},'tests':out,'decision':'P264_BOOTSTRAP_SUPPORTED' if support else 'P264_BOOTSTRAP_NOT_SUPPORTED','limitations':['fund methodology and realized turnover are embedded in adjusted fund returns','Yahoo adjusted prices are research-only'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p264_smallcap_momentum_bootstrap_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
