from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

SECTORS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
TICKERS=SECTORS+['SPY']
WINDOWS={'2001':'2001-01-01','2010':'2010-01-01','2020':'2020-01-01','2022':'2022-01-01'}
LOOKBACK=12
TOPK=3
COST_BP=25

def metrics(r):
    q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q)
    ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12))
    return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}

def build(ret):
    sig=ret[SECTORS].rolling(LOOKBACK,min_periods=LOOKBACK).std().shift(1)
    w=pd.DataFrame(0.0,index=ret.index,columns=SECTORS)
    for dt,row in sig.iterrows():
        if row.notna().sum()==len(SECTORS):
            chosen=row.nsmallest(TOPK).index
            w.loc[dt,chosen]=1.0/TOPK
    gross=(w*ret[SECTORS]).sum(axis=1)
    turnover=0.5*w.diff().abs().sum(axis=1)
    first=w.sum(axis=1).gt(0).idxmax() if w.sum(axis=1).gt(0).any() else None
    if first is not None: turnover.loc[first]=1.0
    net=gross-(COST_BP/10000.0)*turnover
    eq=ret[SECTORS].mean(axis=1).copy()
    if len(eq): eq.iloc[0]-=COST_BP/10000.0
    return net,eq,w,turnover

raw=yf.download(TICKERS,start='1999-12-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=close[TICKERS].dropna().resample('ME').last(); ret=m.pct_change().dropna(); cand,matched,w,to=build(ret); out={}
for name,start in WINDOWS.items():
    ix=ret.index>=pd.Timestamp(start); a=cand.loc[ix]; b=matched.loc[ix]; s=ret.loc[ix,'SPY'].copy()
    if len(s): s.iloc[0]-=COST_BP/10000.0
    cm,mm,sm=metrics(a),metrics(b),metrics(s); folds=[]
    loc=np.flatnonzero(ix)
    for i,sub in enumerate(np.array_split(loc,5),1):
        aa=cand.iloc[sub]; bb=matched.iloc[sub]
        folds.append({'fold':i,'matched_excess_cagr':metrics(aa)['cagr']-metrics(bb)['cagr']})
    out[name]={'candidate':cm,'matched_equalweight':mm,'spy_context':sm,'matched_excess_cagr':cm['cagr']-mm['cagr'],'vs_spy_cagr':cm['cagr']-sm['cagr'],'positive_matched_folds':sum(x['matched_excess_cagr']>0 for x in folds),'avg_monthly_turnover':float(to.loc[ix].mean()),'folds':folds}
a=out['2001']; b=out['2010']; c=out['2020']; d=out['2022']
support=(a['matched_excess_cagr']>0 and b['matched_excess_cagr']>0 and c['matched_excess_cagr']>0 and d['matched_excess_cagr']>0 and a['positive_matched_folds']>=4 and a['candidate']['maxdd']>=a['matched_equalweight']['maxdd'])
res={'schema':'research.p265_sector_lowvol_r1','parent':'P265','claim':'A prospectively fixed cross-sectional low-volatility selector across the nine long-history SPDR sectors creates durable after-cost excess versus an equal-weight same-universe control by holding the three sectors with lowest trailing 12-month realized monthly volatility for the next month.','contract':{'universe':SECTORS,'signal':'trailing 12 monthly-return standard deviation, shifted one month','top_k':TOPK,'holding':'next month equal-weight selected sectors','cost_bps_per_one_way_turnover':COST_BP,'matched_control':'same-universe equal weight','opportunity_context':'SPY','windows':WINDOWS,'folds':5,'gate':'positive matched excess all windows; >=4/5 positive full-history folds; candidate maxDD no worse than matched','no_universe_lookback_topk_window_threshold_or_parameter_search':True},'tests':out,'decision':'P265_SECTOR_LOWVOL_SUPPORTED' if support else 'P265_SECTOR_LOWVOL_NOT_SUPPORTED','limitations':['ETF adjusted prices are research-only','sector membership fixed to long-history SPDR set; fund/index methodology embedded in returns'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p265_sector_lowvol_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
