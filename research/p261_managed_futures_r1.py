from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS=['DBMF','BIL','SPY']
WINDOWS={'2020':'2020-01-01','2022':'2022-01-01'}
COST_BP=10

def metrics(r):
    q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q)
    ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12))
    return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}

def endpoint_cost(r):
    q=pd.Series(r,dtype=float).dropna().copy(); f=COST_BP/10000
    if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
    return q
raw=yf.download(TICKERS,start='2019-01-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=close[TICKERS].dropna().resample('ME').last().pct_change().dropna(); out={}
for name,start in WINDOWS.items():
    q=r.loc[r.index>=pd.Timestamp(start)]; a=endpoint_cost(q.DBMF); b=endpoint_cost(q.BIL); s=endpoint_cost(q.SPY)
    am,bm,sm=metrics(a),metrics(b),metrics(s); folds=[]
    for i,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
        aa=metrics(endpoint_cost(q.DBMF.iloc[ix])); bb=metrics(endpoint_cost(q.BIL.iloc[ix])); folds.append({'fold':i,'vs_cash_cagr':aa['cagr']-bb['cagr']})
    out[name]={'candidate':am,'cash_bil':bm,'spy':sm,'cash_excess_cagr':am['cagr']-bm['cagr'],'spy_corr':float(q.DBMF.corr(q.SPY)),'positive_cash_folds':sum(x['vs_cash_cagr']>0 for x in folds),'folds':folds}
a,b=out['2020'],out['2022']
support=(a['cash_excess_cagr']>0 and b['cash_excess_cagr']>0 and a['positive_cash_folds']>=4 and a['candidate']['sharpe_rf0']>=0.5 and a['candidate']['maxdd']>=-0.25 and abs(a['spy_corr'])<=0.4)
res={'schema':'research.p261_managed_futures_r1','parent':'P261','claim':'A prospectively fixed managed-futures sleeve represented by DBMF provides durable after-cost alternative alpha versus investable cash with low equity correlation.','contract':{'candidate':'DBMF','matched_control':'BIL','opportunity_context':'SPY','cost_bps':COST_BP,'windows':WINDOWS,'folds':5,'gate':'positive cash excess both windows; >=4/5 positive 2020+ cash folds; Sharpe >=0.5; maxDD >= -25%; absolute SPY monthly correlation <=0.4','no_fund_window_weight_threshold_or_parameter_search':True},'tests':out,'decision':'P261_MANAGED_FUTURES_SUPPORTED' if support else 'P261_MANAGED_FUTURES_NOT_SUPPORTED','limitations':['DBMF live history is short and begins in 2019','BIL is an investable cash proxy','Yahoo adjusted prices are research-only'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p261_managed_futures_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
