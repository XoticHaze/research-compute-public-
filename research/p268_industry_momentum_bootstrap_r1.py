from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

INDUSTRIES=['XAR','XBI','XHB','XME','XOP','XPH','XRT','XSD','XSW','XTN','KRE']
WINDOWS={'2012':'2012-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
TOPK=3
COST_BP=25
BLOCK=12
REPS=5000
SEED=268

def build(close):
    ret=close[INDUSTRIES].pct_change(); score=close[INDUSTRIES].shift(1)/close[INDUSTRIES].shift(12)-1
    w=pd.DataFrame(0.0,index=close.index,columns=INDUSTRIES)
    for dt,row in score.iterrows():
        if row.notna().sum()==len(INDUSTRIES): w.loc[dt,row.nlargest(TOPK).index]=1/TOPK
    gross=(w*ret).sum(axis=1); turn=0.5*w.diff().abs().sum(axis=1); active=w.sum(axis=1).gt(0)
    if active.any(): turn.loc[active.idxmax()]=1.0
    cand=gross-(COST_BP/10000)*turn; matched=ret.mean(axis=1).copy()
    if active.any(): matched.loc[active.idxmax()]-=COST_BP/10000
    return cand,matched,active

def boot(x, seed):
    x=np.asarray(pd.Series(x,dtype=float).dropna()); n=len(x); rng=np.random.default_rng(seed); starts=np.arange(max(1,n-BLOCK+1)); vals=np.empty(REPS)
    for j in range(REPS):
        draw=[]
        while len(draw)<n:
            s=int(rng.choice(starts)); draw.extend(x[s:min(s+BLOCK,n)].tolist())
        vals[j]=float(np.mean(draw[:n])*12)
    return {'months':int(n),'median_annualized_excess':float(np.median(vals)),'p05_annualized_excess':float(np.quantile(vals,0.05)),'p95_annualized_excess':float(np.quantile(vals,0.95)),'probability_excess_le_zero':float(np.mean(vals<=0))}

raw=yf.download(INDUSTRIES,start='2010-01-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=close[INDUSTRIES].dropna().resample('ME').last(); cand,matched,active=build(m); out={}
for name,start in WINDOWS.items():
    ix=(m.index>=pd.Timestamp(start)) & active; ex=(cand.loc[ix]-matched.loc[ix]).dropna(); out[name]={'observed_annualized_excess':float(ex.mean()*12),'bootstrap':boot(ex,SEED+int(name))}
def gate(z): return z['p05_annualized_excess']>0 and z['probability_excess_le_zero']<0.10
support=all(gate(out[w]['bootstrap']) for w in WINDOWS)
res={'schema':'research.p268_industry_momentum_bootstrap_r1','parent':'P266/P268','claim':'The fixed P266 industry-momentum matched excess survives a paired serial-dependence-preserving 12-month moving-block bootstrap without changing universe, signal, top-k, costs, or windows.','contract':{'universe':INDUSTRIES,'signal':'P266 fixed 12-1 month-end momentum','top_k':TOPK,'cost_bps_per_one_way_turnover':COST_BP,'windows':WINDOWS,'block_months':BLOCK,'bootstrap_reps':REPS,'seed':SEED,'gate':'p05 annualized matched excess >0 and P(excess<=0)<10% in every predeclared window','no_parameter_or_architecture_change':True},'tests':out,'decision':'P268_BOOTSTRAP_SUPPORTED' if support else 'P268_BOOTSTRAP_NOT_SUPPORTED','limitations':['ETF adjusted prices are research-only','paired bootstrap preserves monthly serial dependence only approximately through fixed-length blocks'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p268_industry_momentum_bootstrap_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
