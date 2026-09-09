#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np
import pandas as pd
import futures_crossmarket_screen_r1 as loader

TICKERS={'MES':'MES=F','ES':'ES=F'}
START=pd.Timestamp('2019-05-03')
DELAYS=(1,3,5)
COSTS=(5.0,10.0)

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1) if len(r) else None

def eval_one(close,delay,bp,start=None):
    daily=close.index
    mclose=close.resample('ME').last().dropna()
    month_dates=[]
    for period in mclose.index.to_period('M'):
        loc=close.index[close.index.to_period('M')==period]
        if len(loc): month_dates.append(loc[-1])
    mom=close/close.shift(252)-1
    sig={dt:float(mom.loc[dt]>0) for dt in month_dates if dt in mom.index and pd.notna(mom.loc[dt])}
    labels=[dt for dt in month_dates if dt in sig]
    rec=[]; prev=0.0
    for i in range(len(labels)-1):
        dt,nxt=labels[i],labels[i+1]
        a=daily.get_loc(dt)+delay; z=daily.get_loc(nxt)+delay
        if a>=len(daily) or z>=len(daily): continue
        exit_dt=daily[z]
        if start is not None and exit_dt<pd.Timestamp(start): continue
        w=sig[dt]; r=float(close.iloc[z]/close.iloc[a]-1); turn=abs(w-prev); net=w*r-turn*bp/10000.0
        rec.append((exit_dt,net,r,w)); prev=w
    f=pd.DataFrame(rec,columns=['date','candidate','underlying','weight']).set_index('date')
    matched=float(f.weight.mean())*f.underlying
    folds=[]
    for j,ids in enumerate(np.array_split(np.arange(len(f)),5),1):
        q=f.iloc[ids]; qb=float(f.weight.mean())*q.underlying
        folds.append({'fold':j,'start':q.index.min().date().isoformat(),'end':q.index.max().date().isoformat(),'excess_cagr':cagr(q.candidate)-cagr(qb)})
    return {'months':len(f),'start':f.index.min().date().isoformat(),'end':f.index.max().date().isoformat(),'candidate_cagr':cagr(f.candidate),'matched_cagr':cagr(matched),'excess_cagr':cagr(f.candidate)-cagr(matched),'positive_folds':sum(x['excess_cagr']>0 for x in folds),'folds':folds,'mean_exposure':float(f.weight.mean())}

def main():
    loader.MIN_ROWS=700; raw={}; src={}
    for k,t in TICKERS.items():
        df,h=loader.load_market(t); raw[k]=df['Close'].astype(float); src[k]=h
    common=raw['MES'].index.intersection(raw['ES'].index); common=common[common>=START]; px={k:v.reindex(common) for k,v in raw.items()}
    out={'schema':'research.mes_es_trend_causal_delay_r6','parent':'futures_micro_trend252','scientific_contract':{'mechanism':'unchanged prior-252-session return sign; long/cash for next monthly interval','entry_exit_delays_trading_days':list(DELAYS),'costs_bps':list(COSTS),'matched_control':'same representation over identical delayed interval at candidate mean exposure','windows':['full common era','2022-forward'],'no_parameter_search':True,'no_canonical_roll_claim':True},'source_sha256':src,'tests':{}}
    for k in TICKERS:
        out['tests'][k]={}
        for d in DELAYS:
            out['tests'][k][str(d)]={}
            for bp in COSTS:
                out['tests'][k][str(d)][str(bp)]={'full':eval_one(px[k],d,bp),'2022_forward':eval_one(px[k],d,bp,'2022-01-01')}
    p=out['tests']['MES']; q=out['tests']['ES']
    def ok(x): return x['1']['5.0']['full']['excess_cagr']>0 and x['1']['5.0']['full']['positive_folds']>=3 and x['3']['5.0']['full']['excess_cagr']>0 and x['1']['5.0']['2022_forward']['excess_cagr']>0
    out['decision']='MES_ES_TREND_CAUSAL_DELAY_SUPPORTED' if ok(p) and ok(q) else ('MES_TREND_CAUSAL_DELAY_ONLY' if ok(p) else 'MES_ES_TREND_CAUSAL_DELAY_WEAK')
    Path('mes_es_trend_causal_delay_r6.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'MES':p,'ES':q},sort_keys=True))
if __name__=='__main__': main()
