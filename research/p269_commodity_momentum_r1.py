from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ASSETS=['GLD','SLV','USO','UNG','DBA','DBB']
TICKERS=ASSETS+['SPY']
WINDOWS={'2008':'2008-01-01','2010':'2010-01-01','2020':'2020-01-01','2022':'2022-01-01'}
TOPK=2
COST_BP=25

def metrics(r):
    q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q)
    ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12))
    return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}

def build(close):
    ret=close[ASSETS].pct_change(); score=close[ASSETS].shift(1)/close[ASSETS].shift(12)-1
    w=pd.DataFrame(0.0,index=close.index,columns=ASSETS)
    for dt,row in score.iterrows():
        if row.notna().sum()==len(ASSETS): w.loc[dt,row.nlargest(TOPK).index]=1/TOPK
    gross=(w*ret).sum(axis=1); turn=0.5*w.diff().abs().sum(axis=1); active=w.sum(axis=1).gt(0)
    if active.any(): turn.loc[active.idxmax()]=1.0
    cand=gross-(COST_BP/10000)*turn; matched=ret.mean(axis=1).copy()
    if active.any(): matched.loc[active.idxmax()]-=COST_BP/10000
    return cand,matched,turn,active

raw=yf.download(TICKERS,start='2006-01-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=close[TICKERS].dropna().resample('ME').last(); cand,matched,turn,active=build(m); spy=m.SPY.pct_change(); out={}
for name,start in WINDOWS.items():
    ix=(m.index>=pd.Timestamp(start)) & active; a=cand.loc[ix]; b=matched.loc[ix]; s=spy.loc[ix].copy()
    if len(s): s.iloc[0]-=COST_BP/10000
    cm,mm,sm=metrics(a),metrics(b),metrics(s); loc=np.flatnonzero(ix); folds=[]
    for i,sub in enumerate(np.array_split(loc,5),1):
        aa=cand.iloc[sub]; bb=matched.iloc[sub]; folds.append({'fold':i,'matched_excess_cagr':metrics(aa)['cagr']-metrics(bb)['cagr']})
    out[name]={'candidate':cm,'matched_equalweight':mm,'spy_context':sm,'matched_excess_cagr':cm['cagr']-mm['cagr'],'vs_spy_cagr':cm['cagr']-sm['cagr'],'positive_matched_folds':sum(x['matched_excess_cagr']>0 for x in folds),'avg_monthly_turnover':float(turn.loc[ix].mean()),'folds':folds}
a=out['2008']; support=(all(out[w]['matched_excess_cagr']>0 for w in WINDOWS) and a['positive_matched_folds']>=4 and a['candidate']['maxdd']>=a['matched_equalweight']['maxdd']-0.05)
res={'schema':'research.p269_commodity_momentum_r1','parent':'P269','claim':'A prospectively fixed 12-1 cross-sectional momentum selector over six liquid commodity exposures creates durable after-cost excess versus a same-universe equal-weight control, testing a non-equity return-source architecture.','contract':{'universe':ASSETS,'signal':'12-1 month-end momentum using information through prior month','top_k':TOPK,'holding':'next month equal-weight selected commodity exposures','cost_bps_per_one_way_turnover':COST_BP,'matched_control':'same-universe equal weight','opportunity_context':'SPY','windows':WINDOWS,'folds':5,'gate':'positive matched excess all windows; >=4/5 positive full-history folds; maxDD no worse than matched by >5pp','no_universe_horizon_topk_window_threshold_or_parameter_search':True},'tests':out,'decision':'P269_COMMODITY_MOMENTUM_SUPPORTED' if support else 'P269_COMMODITY_MOMENTUM_NOT_SUPPORTED','limitations':['commodity ETFs embed futures roll/collateral/index methodology and are not spot commodities','ETF adjusted prices are research-only'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p269_commodity_momentum_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
