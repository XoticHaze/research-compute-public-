from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import p81_p46_riskoff_deactivation_r1 as p81


def cagr(r: pd.Series) -> float:
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)

def rolling(frame: pd.DataFrame,bps:int,window:int,baseline:str):
    h=frame.hybrid_gross-frame.hybrid_turnover*bps/10000
    if baseline=='active': b=frame.active_gross-frame.active_turnover*bps/10000
    else: b=frame.ew
    vals=[]
    for i in range(window,len(frame)+1): vals.append(cagr(h.iloc[i-window:i])-cagr(b.iloc[i-window:i]))
    a=np.asarray(vals,float); return {'windows':len(a),'positive_fraction':float((a>0).mean()),'median_excess_cagr':float(np.median(a)),'p10_excess_cagr':float(np.quantile(a,.1)),'p90_excess_cagr':float(np.quantile(a,.9))}
def bootstrap(frame:pd.DataFrame,bps:int,baseline:str,n:int=5000,block:int=12):
    h=frame.hybrid_gross-frame.hybrid_turnover*bps/10000
    b=(frame.active_gross-frame.active_turnover*bps/10000) if baseline=='active' else frame.ew
    x=(h-b).to_numpy(); rng=np.random.default_rng(20260909); vals=[]; L=len(x)
    for _ in range(n):
        pieces=[]
        while sum(len(z) for z in pieces)<L:
            s=int(rng.integers(0,max(1,L-block+1))); pieces.append(x[s:s+block])
        samp=np.concatenate(pieces)[:L]; vals.append(float(samp.mean()*12))
    a=np.asarray(vals); return {'annualized_mean_excess':float(x.mean()*12),'bootstrap_95pct':[float(np.quantile(a,.025)),float(np.quantile(a,.975))],'p_excess_le_zero':float((a<=0).mean()),'block_months':block,'replicates':n}
def main():
    close=p81.base.load(p81.SYMBOLS); f=p81.build(close)
    out={'schema':'research.p85_p81_serial_persistence_r1','parent_ids':['P46','P81','P85'],'scientific_contract':{'mechanism':'frozen P81 regime-conditioned hybrid','comparators':['original active P46','same-universe equal weight'],'costs_bps':[25,50],'rolling_windows_months':[36,60],'bootstrap':'12-month moving-block bootstrap, 5000 reps, deterministic seed','no_parameter_tuning':True},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'tests':{}}
    for bps in (25,50):
        out['tests'][str(bps)]={}
        for baseline in ('active','ew'):
            out['tests'][str(bps)][baseline]={'rolling36':rolling(f,bps,36,baseline),'rolling60':rolling(f,bps,60,baseline),'bootstrap':bootstrap(f,bps,baseline)}
    a=out['tests']['25']['active']; e=out['tests']['25']['ew']; a50=out['tests']['50']['active']
    supported=a['rolling60']['positive_fraction']>=.6 and e['rolling60']['positive_fraction']>=.6 and a['bootstrap']['p_excess_le_zero']<=.2 and a50['bootstrap']['annualized_mean_excess']>0
    out['decision']='SUPPORTED_PERSISTENT_REGIME_IMPROVEMENT' if supported else 'PERSISTENCE_INSUFFICIENT_PARK_OR_REFRAME'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p85_p81_serial_persistence_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'25_active':a,'25_ew':e,'50_active':a50},sort_keys=True))
if __name__=='__main__': main()
