from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS=['BTAL','BIL','SPY']
WINDOWS={'2012':'2012-01-01','2020':'2020-01-01','2022':'2022-01-01'}
COST_BP=10

def metrics(r):
    q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q)
    ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12))
    return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}

def endpoint_cost(r,bps=COST_BP):
    q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
    if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
    return q

raw=yf.download(TICKERS,start='2011-01-01',end='2026-09-03',auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=close[TICKERS].dropna().resample('ME').last(); ret=m.pct_change().dropna(); out={}
for name,start in WINDOWS.items():
    q=ret.loc[ret.index>=pd.Timestamp(start)].copy(); cand=endpoint_cost(q.BTAL); cash=endpoint_cost(q.BIL); spy=endpoint_cost(q.SPY)
    cm=metrics(cand); bm=metrics(cash); sm=metrics(spy); folds=[]
    for i,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
        a=endpoint_cost(q.BTAL.iloc[ix]); b=endpoint_cost(q.BIL.iloc[ix])
        folds.append({'fold':i,'vs_cash_cagr':metrics(a)['cagr']-metrics(b)['cagr']})
    out[name]={'candidate':cm,'cash_bil':bm,'spy':sm,'cash_excess_cagr':cm['cagr']-bm['cagr'],'vs_spy_cagr':cm['cagr']-sm['cagr'],'candidate_spy_monthly_corr':float(q.BTAL.corr(q.SPY)),'positive_cash_folds':sum(x['vs_cash_cagr']>0 for x in folds),'folds':folds}
a=out['2012']; b=out['2020']; c=out['2022']
support=(a['cash_excess_cagr']>0 and b['cash_excess_cagr']>0 and c['cash_excess_cagr']>0 and a['positive_cash_folds']>=4 and a['candidate']['sharpe_rf0']>=0.4 and a['candidate']['maxdd']>=-0.25 and a['candidate_spy_monthly_corr']<=0.2)
res={'schema':'research.p255_antibeta_r1','parent':'P255','claim':'A prospectively fixed anti-beta long/short equity sleeve represented by BTAL provides durable after-cost alternative alpha versus cash with low equity beta, rather than being judged as a long-equity replacement.','contract':{'candidate':'BTAL','matched_control':'BIL cash proxy','opportunity_context':'SPY','cost_bps':COST_BP,'windows':WINDOWS,'folds':5,'gate':'positive cash excess all windows; >=4/5 positive 2012+ cash folds; Sharpe >=0.4; maxDD no worse than -25%; monthly SPY correlation <=0.2','no_fund_window_weight_threshold_or_parameter_search':True},'tests':out,'decision':'P255_ANTIBETA_SUPPORTED' if support else 'P255_ANTIBETA_NOT_SUPPORTED','limitations':['BTAL history limits the sample','BIL is an investable cash proxy rather than a financing-rate reconstruction','Yahoo adjusted prices are research-only'],'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p255_antibeta_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
