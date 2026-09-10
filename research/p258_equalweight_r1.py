from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS=['RSP','SPY','IWB']
WINDOWS={'2004':'2004-01-01','2010':'2010-01-01','2020':'2020-01-01','2022':'2022-01-01'}
COST_BP=10

def metrics(r):
    q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q)
    ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12))
    return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}

def endpoint_cost(r,bps=COST_BP):
    q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
    if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
    return q

raw=yf.download(TICKERS,start='2003-01-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=close[TICKERS].dropna().resample('ME').last(); ret=m.pct_change().dropna(); out={}
for name,start in WINDOWS.items():
    q=ret.loc[ret.index>=pd.Timestamp(start)].copy(); cand=endpoint_cost(q.RSP); matched=endpoint_cost(q.SPY); broad=endpoint_cost(q.IWB)
    cm=metrics(cand); mm=metrics(matched); bm=metrics(broad); folds=[]
    for i,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
        a=endpoint_cost(q.RSP.iloc[ix]); b=endpoint_cost(q.SPY.iloc[ix])
        folds.append({'fold':i,'vs_spy_cagr':metrics(a)['cagr']-metrics(b)['cagr']})
    out[name]={'candidate':cm,'matched_spy':mm,'broad_iwb':bm,'matched_excess_cagr':cm['cagr']-mm['cagr'],'vs_iwb_cagr':cm['cagr']-bm['cagr'],'positive_matched_folds':sum(x['vs_spy_cagr']>0 for x in folds),'folds':folds}
a=out['2004']; b=out['2010']; c=out['2020']; d=out['2022']
support=(a['matched_excess_cagr']>0 and b['matched_excess_cagr']>0 and c['matched_excess_cagr']>0 and d['matched_excess_cagr']>0 and a['positive_matched_folds']>=4 and a['candidate']['maxdd']>=a['matched_spy']['maxdd']-0.05)
res={'schema':'research.p258_equalweight_r1','parent':'P258','claim':'A prospectively fixed S&P 500 equal-weight implementation represented by RSP creates durable after-cost excess versus cap-weighted SPY through systematic rebalancing and anti-concentration rather than discretionary selection.','contract':{'candidate':'RSP','matched_control':'SPY','secondary_broad_control':'IWB','cost_bps':COST_BP,'windows':WINDOWS,'folds':5,'gate':'positive matched excess in all windows; >=4/5 positive full-history matched folds; maxDD no worse than matched by >5pp','no_fund_window_weight_threshold_or_parameter_search':True},'tests':out,'decision':'P258_EQUALWEIGHT_SUPPORTED' if support else 'P258_EQUALWEIGHT_NOT_SUPPORTED','limitations':['fund/index methodology and realized turnover are embedded in adjusted fund returns','Yahoo adjusted prices are research-only'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p258_equalweight_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
