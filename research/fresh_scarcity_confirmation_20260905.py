from __future__ import annotations
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

START='2014-01-01'; END='2026-09-03'; DELAY=1; HOLD=20; FOLDS=6; MIN_TRAIN=756; PURGE=22; COST_TRAIN=25.0
TRAIN=('AMAT','APH','KLAC','LRCX','TXN','NXPI','ADI')
FRESH=('QCOM','INTC','ON','MPWR','SWKS','LSCC','TER','ASX')
CONTEXT=('SMH','QQQ')
FULL=['mom5','mom20','mom60','mom100','mom20_z252','mom20_accel5','vol20','vol20_z252','distance_high60','rs_smh20','rs_smh60','rs_qqq20','rs_qqq60','smh_mom20','smh_mom100','qqq_mom20','qqq_mom100','survivor_breadth_positive20','survivor_cross_section_mom20_pct']
GENERIC=['mom5','mom20','mom60','mom100','mom20_z252','mom20_accel5','vol20','vol20_z252','distance_high60','rs_qqq20','rs_qqq60','qqq_mom20','qqq_mom100']
OUT=Path('fresh_scarcity_confirmation_receipt_20260905.json')

def epoch(s): return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp())
def load(sym):
    q=urlencode({'period1':epoch(START),'period2':epoch(END),'interval':'1d','events':'history','includeAdjustedClose':'true'})
    req=Request(f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{q}',headers={'User-Agent':'Mozilla/5.0 research-compute/1.0'})
    with urlopen(req,timeout=30) as r: p=json.loads(r.read().decode())
    x=(p.get('chart',{}).get('result') or [None])[0]
    if not x: raise RuntimeError(f'{sym}: no chart result')
    ind=x.get('indicators',{}); adj=(ind.get('adjclose') or [{}])[0].get('adjclose'); close=adj or (ind.get('quote') or [{}])[0].get('close')
    return pd.DataFrame({'timestamp':pd.to_datetime(x.get('timestamp') or [],unit='s',utc=True),'price':pd.to_numeric(pd.Series(close),errors='coerce')}).dropna().sort_values('timestamp').drop_duplicates('timestamp',keep='last').reset_index(drop=True)
def folds(n):
    e=np.linspace(MIN_TRAIN,n-(HOLD+DELAY+1),FOLDS+1,dtype=int); return [(int(e[i]),int(e[i+1])) for i in range(FOLDS)]
def engineer(prices,cal):
    o={}
    for s,p in prices.items():
        d=pd.DataFrame({'timestamp':cal,'price':p.to_numpy(float)}); d['ret1']=d.price.pct_change()
        for n in (5,20,60,100): d[f'mom{n}']=d.price.pct_change(n)
        d['vol20']=d.ret1.rolling(20,min_periods=20).std(ddof=0); pm=d.mom20.shift(1); pv=d.vol20.shift(1)
        mm=pm.rolling(252,min_periods=126).mean(); ms=pm.rolling(252,min_periods=126).std(ddof=0).replace(0,np.nan)
        vm=pv.rolling(252,min_periods=126).mean(); vs=pv.rolling(252,min_periods=126).std(ddof=0).replace(0,np.nan)
        d['mom20_z252']=(d.mom20-mm)/ms; d['vol20_z252']=(d.vol20-vm)/vs; d['mom20_accel5']=d.mom20-d.mom20.shift(5); d['distance_high60']=d.price/d.price.rolling(60,min_periods=60).max()-1; o[s]=d
    smh,qqq=o['SMH'],o['QQQ']; surv=pd.DataFrame({s:o[s].mom20 for s in TRAIN}); breadth=(surv>0).mean(axis=1)
    for s in (*TRAIN,*FRESH):
        d=o[s]; d['rs_smh20']=d.mom20-smh.mom20; d['rs_smh60']=d.mom60-smh.mom60; d['rs_qqq20']=d.mom20-qqq.mom20; d['rs_qqq60']=d.mom60-qqq.mom60
        d['smh_mom20']=smh.mom20; d['smh_mom100']=smh.mom100; d['qqq_mom20']=qqq.mom20; d['qqq_mom100']=qqq.mom100; d['survivor_breadth_positive20']=breadth
        d['survivor_cross_section_mom20_pct']=pd.Series([np.nan if pd.isna(v) else float((surv.iloc[i]<=v).mean()) for i,v in enumerate(d.mom20)],index=d.index)
        d['target']=(d.price.shift(-(DELAY+HOLD))/d.price.shift(-DELAY)-1)*10000-COST_TRAIN
    return o
def frame(symbols,data,fs,features):
    rows=[]
    for s in symbols:
        d=data[s].copy(); d['symbol']=s; d['signal_i']=np.arange(len(d)); fc=np.zeros(len(d),dtype=int)
        for f,(a,b) in enumerate(fs,1): fc[a:max(a,b-(DELAY+HOLD))]=f
        d['fold']=fc; rows.append(d[d.fold>0][['symbol','signal_i','fold',*features,'target']])
    return pd.concat(rows,ignore_index=True).replace([np.inf,-np.inf],np.nan).dropna(subset=features+['target'])
def spearman(a,b):
    if len(a)<3 or np.std(a)<=0 or np.std(b)<=0:return None
    return float(pd.Series(a).rank().corr(pd.Series(b).rank()))
def fit(train,features):
    m=Pipeline([('scale',StandardScaler()),('ridge',Ridge(alpha=10.0))]); m.fit(train[features].to_numpy(float),train.target.to_numpy(float)); return m
def summarize(rows,cost):
    top=[r['top']-cost for r in rows]; ew=[r['ew']-cost for r in rows]; smh=[r['smh']-cost for r in rows]; ic=[r['ic'] for r in rows if r['ic'] is not None]
    mean=lambda x:None if not x else float(np.mean(x))
    return {'decisions':len(rows),'mean_top2_net_bps':mean(top),'mean_admitted_ew_net_bps':mean(ew),'mean_smh_net_bps':mean(smh),'mean_top2_excess_vs_admitted_ew_bps':mean([a-b for a,b in zip(top,ew)]),'mean_top2_excess_vs_smh_bps':mean([a-b for a,b in zip(top,smh)]),'mean_rank_ic':mean(ic)}
def run_arm(features):
    syms=(*TRAIN,*FRESH,*CONTEXT); raw={s:load(s) for s in syms}; cutoff=min(d.iloc[-1].timestamp for d in raw.values()); sets=[set(d.loc[d.timestamp<=cutoff,'timestamp']) for d in raw.values()]; cal=pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(cal)<1500: raise RuntimeError(f'insufficient common calendar {len(cal)}')
    prices={s:raw[s].set_index('timestamp').price.reindex(cal) for s in raw}; data=engineer(prices,cal); fs=folds(len(cal)); tr=frame(TRAIN,data,fs,features); decisions=[]
    for f in range(2,7):
        start,stop=fs[f-1]; train=tr[tr.signal_i<start-PURGE]; model=fit(train,features); i=start; safe=stop-(DELAY+HOLD)
        while i<safe:
            ei=i+DELAY; xi=ei+HOLD; c=[]
            for s in FRESH:
                vals=data[s].loc[i,features].to_numpy(float)
                if not np.isfinite(vals).all(): continue
                sc=float(model.predict(np.asarray([vals]))[0])
                if sc<=0: continue
                gross=float(prices[s].iloc[xi]/prices[s].iloc[ei]-1)*10000; c.append((s,sc,gross))
            if len(c)>=2:
                c.sort(key=lambda z:(-z[1],z[0])); top=c[:2]; decisions.append({'fold':f,'top':float(np.mean([z[2] for z in top])),'ew':float(np.mean([z[2] for z in c])),'smh':float(prices['SMH'].iloc[xi]/prices['SMH'].iloc[ei]-1)*10000,'ic':spearman(np.asarray([z[1] for z in c]),np.asarray([z[2] for z in c]))})
            i+=HOLD
    foldsums=[]
    for f in range(2,7):
        s=summarize([r for r in decisions if r['fold']==f],200); s['fold']=f; foldsums.append(s)
    agg=summarize(decisions,200); agg.update({'positive_top2_folds':sum((r['mean_top2_net_bps'] or -1)>0 for r in foldsums),'admitted_ew_winning_folds':sum((r['mean_top2_excess_vs_admitted_ew_bps'] or -1)>0 for r in foldsums),'smh_winning_folds':sum((r['mean_top2_excess_vs_smh_bps'] or -1)>0 for r in foldsums),'positive_rank_ic_folds':sum((r['mean_rank_ic'] or -1)>0 for r in foldsums)})
    passed=bool(len(foldsums)==5 and agg['mean_top2_net_bps']>0 and agg['mean_top2_excess_vs_admitted_ew_bps']>0 and agg['mean_top2_excess_vs_smh_bps']>0 and agg['mean_rank_ic']>0 and agg['positive_top2_folds']>=3 and agg['admitted_ew_winning_folds']>=3 and agg['smh_winning_folds']>=3 and agg['positive_rank_ic_folds']>=3)
    return {'common_cutoff':cutoff.isoformat(),'common_calendar_rows':len(cal),'aggregate_200bps':agg,'folds_200bps':foldsums,'decision':'PASS' if passed else 'FAIL'}
def main():
    full=run_arm(FULL); generic=run_arm(GENERIC); decision='REJECT_FRESH_SCARCITY_RANKER_CONFIRMATION' if full['decision']=='FAIL' else ('CONFIRM_INDUSTRY_CONTEXT_SCARCITY_RANKER' if generic['decision']=='FAIL' else 'CONFIRM_SCARCITY_RANKING_NOT_CONTEXT_INCREMENT')
    out={'schema':'public_compute.fresh_scarcity_confirmation.v1','generated_at':datetime.now(timezone.utc).isoformat(),'origin':'research-foundry PR273 frozen science reconstructed as self-contained public execution capsule','train_universe':TRAIN,'fresh_universe':FRESH,'full_19_feature':full,'generic_13_feature':generic,'decision':decision,'research_only':True,'runtime_mutation':False,'live_trading_change':False}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); print('FRESH_SCARCITY_CONFIRMATION='+json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
