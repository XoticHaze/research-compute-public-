#!/usr/bin/env python3
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import futures_crossmarket_screen_r1 as base

START=pd.Timestamp('2019-05-03')
COSTS=(2.5,5.0,10.0)
TICKERS={'MES':'MES=F','ES':'ES=F'}

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else None

def eval_series(close,cost_bps,start=None):
    m=close.resample('ME').last().dropna(); mom=(close/close.shift(252)-1).resample('ME').last().reindex(m.index)
    ret=m.pct_change(); w=(mom.shift(1)>0).astype(float); turn=w.diff().abs().fillna(w.abs()); cand=w*ret-turn*cost_bps/10000.0; matched=float(w.mean())*ret
    f=pd.concat([cand.rename('candidate'),matched.rename('matched'),w.rename('w')],axis=1).dropna()
    if start is not None: f=f.loc[f.index>=pd.Timestamp(start)]
    folds=[]
    for i,ids in enumerate(np.array_split(np.arange(len(f)),5),1):
        q=f.iloc[ids]
        folds.append({'fold':i,'start':str(q.index.min().date()),'end':str(q.index.max().date()),'excess_cagr':cagr(q.candidate)-cagr(q.matched)})
    cm=base.ann_metrics(f.candidate,12); bm=base.ann_metrics(f.matched,12)
    return {'months':len(f),'start':str(f.index.min().date()),'end':str(f.index.max().date()),'candidate':cm,'matched':bm,'excess_cagr':cm['cagr']-bm['cagr'],'positive_folds':sum(x['excess_cagr']>0 for x in folds),'folds':folds,'mean_exposure':float(f.w.mean())}

def main():
    base.MIN_ROWS=700; raw={}; sha={}
    for k,t in TICKERS.items():
        df,h=base.load_market(t); raw[k]=df['Close'].astype(float); sha[k]=h
    common=raw['MES'].index.intersection(raw['ES'].index); common=common[common>=START]
    px={k:v.reindex(common).dropna() for k,v in raw.items()}
    common=px['MES'].index.intersection(px['ES'].index); px={k:v.reindex(common) for k,v in px.items()}
    out={'schema':'research.mes_es_trend_transport_r4','parent':'futures_micro_trend252','scientific_contract':{'mechanism':'unchanged prior-252-session return sign, next month long or cash','representations':TICKERS,'matched_identical_daily_window':True,'windows':['2019-05-forward','2022-forward'],'costs_bps':list(COSTS),'matched_control':'static exposure to same representation at candidate mean exposure','no_parameter_search':True,'no_canonical_roll_claim':True},'source_sha256':sha,'common_daily_window':{'start':str(common.min().date()),'end':str(common.max().date()),'rows':len(common)},'tests':{}}
    for k in TICKERS:
        out['tests'][k]={}
        for bp in COSTS:
            out['tests'][k][str(bp)]={'full_common':eval_series(px[k],bp),'2022_forward':eval_series(px[k],bp,'2022-01-01')}
    pmes=out['tests']['MES']['5.0']; pes=out['tests']['ES']['5.0']
    ok=lambda x: x['full_common']['excess_cagr']>0 and x['full_common']['positive_folds']>=3 and x['2022_forward']['excess_cagr']>0 and x['2022_forward']['positive_folds']>=3
    out['decision']='MES_TREND_MATCHED_ERA_TRANSPORT_SUPPORTED' if ok(pmes) and ok(pes) else ('MES_ONLY_RECENT_REPRESENTATION_EFFECT' if ok(pmes) and not ok(pes) else 'MES_TREND_MATCHED_ERA_TRANSPORT_NOT_SUPPORTED')
    Path('mes_es_trend_transport_r4.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'MES_5':pmes,'ES_5':pes},sort_keys=True))
if __name__=='__main__': main()
