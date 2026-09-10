from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS=['COWZ','IWB','SPY']
WINDOWS={'2017':'2017-01-01','2020':'2020-01-01','2022':'2022-01-01'}
COST_BP=10

def metrics(r):
    q=pd.Series(r,dtype=float).dropna()
    e=(1+q).cumprod(); n=len(q)
    ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12))
    return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}

def endpoint_cost(r,bps=COST_BP):
    q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
    if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
    return q

raw=yf.download(TICKERS,start='2016-01-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=close[TICKERS].dropna().resample('ME').last(); ret=m.pct_change().dropna()
out={}
for name,start in WINDOWS.items():
    q=ret.loc[ret.index>=pd.Timestamp(start)].copy()
    c=endpoint_cost(q.COWZ); matched=endpoint_cost(q.IWB); spy=endpoint_cost(q.SPY)
    cm=metrics(c); mm=metrics(matched); sm=metrics(spy); folds=[]
    for i,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
        a=endpoint_cost(q.COWZ.iloc[ix]); b=endpoint_cost(q.IWB.iloc[ix]); s=endpoint_cost(q.SPY.iloc[ix])
        folds.append({'fold':i,'vs_matched_cagr':metrics(a)['cagr']-metrics(b)['cagr'],'vs_spy_cagr':metrics(a)['cagr']-metrics(s)['cagr']})
    out[name]={'candidate':cm,'matched_iwb':mm,'spy':sm,'matched_excess_cagr':cm['cagr']-mm['cagr'],'vs_spy_cagr':cm['cagr']-sm['cagr'],'positive_matched_folds':sum(x['vs_matched_cagr']>0 for x in folds),'folds':folds}
a=out['2017']; b=out['2020']; c=out['2022']
support=(a['matched_excess_cagr']>0 and b['matched_excess_cagr']>0 and c['matched_excess_cagr']>0 and a['positive_matched_folds']>=4 and a['candidate']['maxdd']>=a['matched_iwb']['maxdd']-0.05 and b['vs_spy_cagr']>=-0.02)
res={'schema':'research.p252_fcf_yield_r1','parent':'P252','claim':'A prospectively fixed US free-cash-flow-yield equity sleeve represented by COWZ creates durable after-cost excess return versus broad-US matched exposure without relying on timing or survivor selection.','contract':{'candidate':'COWZ','matched_control':'IWB','opportunity_control':'SPY','cost_bps':COST_BP,'windows':WINDOWS,'folds':5,'gate':'positive matched excess all windows; >=4/5 positive 2017+ matched folds; maxDD no worse than matched by >5pp; 2020+ SPY opportunity deficit no worse than 2pp','no_fund_window_weight_threshold_or_parameter_search':True},'tests':out,'decision':'P252_FCF_YIELD_SUPPORTED' if support else 'P252_FCF_YIELD_NOT_SUPPORTED','limitations':['COWZ history begins in 2016','Yahoo adjusted prices are research-only'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/p252_fcf_yield_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps(res,sort_keys=True))
