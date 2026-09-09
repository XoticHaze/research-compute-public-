#!/usr/bin/env python3
import json, os, math
from pathlib import Path
import numpy as np
import pandas as pd
os.environ.setdefault('P36_ASSET','SOXX'); os.environ.setdefault('P36_CHILD','C2')
import p36_independent_proxy_validation as base

ASSET='SOXX'; BP=50; DELAYS=(1,3); WINDOWS={'2015_forward':'2015-01-01','2022_forward':'2022-01-01'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')
def mdd(r):
    e=(1+pd.Series(r,dtype=float).fillna(0)).cumprod(); return float((e/e.cummax()-1).min())
def vol(r):
    return float(pd.Series(r,dtype=float).std(ddof=1)*math.sqrt(12))

def build(px,delay):
    common=pd.concat(px,axis=1,join='inner').dropna().sort_index(); idx=common.index
    mes=pd.Series(common.index,index=common.index).groupby(common.index.to_period('M')).max().tolist(); mes=[pd.Timestamp(x) for x in mes]
    m=common.loc[mes]; rel=m[ASSET].pct_change(6)-m['QQQ'].pct_change(6); sig={pd.Timestamp(dt):(1.0 if rel.loc[dt]>0 else 0.0) for dt in m.index if pd.notna(rel.loc[dt])}; labels=list(sig)
    rec=[]; prev=None
    for i in range(len(labels)-1):
        dt,nxt=labels[i],labels[i+1]; a0=idx.get_indexer([dt],method='pad')[0]+delay; z0=idx.get_indexer([nxt],method='pad')[0]+delay
        if a0<0 or z0<0 or z0>=len(idx): continue
        w=sig[dt]; ar=float(common.iloc[z0][ASSET]/common.iloc[a0][ASSET]-1); qr=float(common.iloc[z0]['QQQ']/common.iloc[a0]['QQQ']-1); turn=1.0 if prev is None else abs(w-prev)
        rec.append((idx[z0],w*ar+(1-w)*qr-turn*BP/10000,0.5*ar+0.5*qr,ar,qr)); prev=w
    return pd.DataFrame(rec,columns=['date','candidate','matched','asset','qqq']).set_index('date')

def metrics(f):
    out={'months':len(f),'candidate_cagr':cagr(f.candidate),'matched_cagr':cagr(f.matched),'excess_cagr':cagr(f.candidate)-cagr(f.matched),'asset_cagr':cagr(f.asset),'qqq_cagr':cagr(f.qqq),'candidate_mdd':mdd(f.candidate),'matched_mdd':mdd(f.matched),'candidate_vol':vol(f.candidate),'matched_vol':vol(f.matched)}
    pos=0
    for ids in np.array_split(np.arange(len(f)),5):
        q=f.iloc[ids]
        if len(q) and cagr(q.candidate)>cagr(q.matched): pos+=1
    out['positive_folds']=pos; return out

def main():
    px={}; src={}
    for s in (ASSET,'QQQ'): px[s],src[s]=base.yahoo(s)
    results={}
    for d in DELAYS:
        f=build(px,d); results[str(d)]={k:metrics(f.loc[f.index>=pd.Timestamp(start)]) for k,start in WINDOWS.items()}
    support=all(results[str(d)]['2015_forward']['excess_cagr']>0 and results[str(d)]['2015_forward']['positive_folds']>=3 and results[str(d)]['2022_forward']['excess_cagr']>0 for d in DELAYS)
    out={'schema':'research.p36_soxx_delay_temporal_holdout_r1','parent':'P36','scientific_contract':{'representation':'SOXX_vs_QQQ','model':'unchanged six-month relative momentum selector','cost_bps':BP,'entry_delays_trading_days':list(DELAYS),'windows':WINDOWS,'matched_control':'same shifted intervals static 50/50 SOXX+QQQ','opportunity_controls':['SOXX','QQQ'],'risk_metrics':['max_drawdown','annualized_volatility'],'no_parameter_tuning':True},'sources':src,'results':results,'decision':'P36_SOXX_DELAY_TEMPORAL_PERSISTENCE_SUPPORTED' if support else 'P36_SOXX_DELAY_TEMPORAL_PERSISTENCE_WEAK'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p36_soxx_delay_temporal_holdout_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
