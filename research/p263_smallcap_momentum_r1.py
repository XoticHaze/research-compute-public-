from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS=['XSMO','IJR','IWM','SPY']
WINDOWS={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
COST_BP=10

def metrics(r):
    q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q)
    ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12))
    return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}

def endpoint_cost(r,bps=COST_BP):
    q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
    if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
    return q

raw=yf.download(TICKERS,start='2014-01-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=close[TICKERS].dropna().resample('ME').last(); ret=m.pct_change().dropna(); out={}
for name,start in WINDOWS.items():
    q=ret.loc[ret.index>=pd.Timestamp(start)].copy(); cand=endpoint_cost(q.XSMO); ijr=endpoint_cost(q.IJR); iwm=endpoint_cost(q.IWM); spy=endpoint_cost(q.SPY)
    cm=metrics(cand); jm=metrics(ijr); wm=metrics(iwm); sm=metrics(spy); folds=[]
    for i,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
        a=endpoint_cost(q.XSMO.iloc[ix]); b=endpoint_cost(q.IJR.iloc[ix]); c=endpoint_cost(q.IWM.iloc[ix])
        folds.append({'fold':i,'vs_ijr_cagr':metrics(a)['cagr']-metrics(b)['cagr'],'vs_iwm_cagr':metrics(a)['cagr']-metrics(c)['cagr']})
    out[name]={'candidate':cm,'matched_ijr':jm,'matched_iwm':wm,'spy_context':sm,'vs_ijr_cagr':cm['cagr']-jm['cagr'],'vs_iwm_cagr':cm['cagr']-wm['cagr'],'vs_spy_cagr':cm['cagr']-sm['cagr'],'positive_ijr_folds':sum(x['vs_ijr_cagr']>0 for x in folds),'positive_iwm_folds':sum(x['vs_iwm_cagr']>0 for x in folds),'folds':folds}
a=out['2015']; b=out['2020']; c=out['2022']
support=(a['vs_ijr_cagr']>0 and a['vs_iwm_cagr']>0 and b['vs_ijr_cagr']>0 and b['vs_iwm_cagr']>0 and c['vs_ijr_cagr']>0 and c['vs_iwm_cagr']>0 and a['positive_ijr_folds']>=4 and a['positive_iwm_folds']>=4 and a['candidate']['maxdd']>=a['matched_ijr']['maxdd']-0.05)
res={'schema':'research.p263_smallcap_momentum_r1','parent':'P263','claim':'A prospectively fixed small-cap momentum fund represented by XSMO creates durable after-cost excess versus investable small-cap controls, testing whether the earlier mid-cap momentum evidence transports downward in capitalization without parameter rescue.','contract':{'candidate':'XSMO','matched_controls':['IJR','IWM'],'opportunity_context':'SPY','cost_bps':COST_BP,'windows':WINDOWS,'folds':5,'gate':'positive excess versus both small-cap controls in all windows; >=4/5 positive full-history folds versus each; maxDD no worse than IJR by >5pp','no_fund_window_weight_threshold_or_parameter_search':True},'tests':out,'decision':'P263_SMALLCAP_MOMENTUM_SUPPORTED' if support else 'P263_SMALLCAP_MOMENTUM_NOT_SUPPORTED','limitations':['fund methodology and realized turnover are embedded in adjusted fund returns','Yahoo adjusted prices are research-only'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p263_smallcap_momentum_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
