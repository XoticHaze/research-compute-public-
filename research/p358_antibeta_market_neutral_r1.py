from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

FUND='BTAL'; CONTROLS=['BIL','SPY']; ALL=[FUND]+CONTROLS
START='2011-01-01'; END='2026-09-10'; COST_BP=10
WINDOWS={'2013_plus':'2013-01-01','2018_plus':'2018-01-01','2020_plus':'2020-01-01'}
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna(); r=close.resample('ME').last().pct_change().dropna()

def metrics(q):
    q=pd.Series(q,dtype=float).dropna(); n=len(q)
    if n < 2: return {'months':int(n),'cagr':None,'maxdd':None,'sharpe_rf0':None}
    eq=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12)
    return {'months':int(n),'cagr':float(eq.iloc[-1]**(12/n)-1),'maxdd':float((eq/eq.cummax()-1).min()),'sharpe_rf0':float(q.mean()*12/vol) if vol else None}

x=r[[FUND,'BIL','SPY']].copy()
if len(x):
    f=COST_BP/10000
    x.iloc[0,x.columns.get_loc(FUND)]-=f
    x.iloc[-1,x.columns.get_loc(FUND)]-=f
rows={}
for name,start in WINDOWS.items():
    q=x.loc[x.index>=pd.Timestamp(start)]
    a,b,s=metrics(q[FUND]),metrics(q.BIL),metrics(q.SPY)
    folds=[]
    for ix in np.array_split(np.arange(len(q)),5):
        z=q.iloc[ix]
        if len(z)<2: continue
        folds.append(metrics(z[FUND])['cagr']-metrics(z.BIL)['cagr'])
    beta=float(q[FUND].cov(q.SPY)/q.SPY.var()) if q.SPY.var() else None
    rows[name]={'fund':a,'BIL':b,'SPY':s,'cash_excess_cagr':a['cagr']-b['cagr'],'vs_SPY_cagr':a['cagr']-s['cagr'],'positive_cash_excess_folds':sum(v>0 for v in folds),'fold_cash_excess_cagr':folds,'realized_SPY_beta':beta}
passes=sum(v['cash_excess_cagr']>0 and v['positive_cash_excess_folds']>=3 for v in rows.values())
beta_guard=all(abs(v['realized_SPY_beta'])<=0.5 for v in rows.values())
supported=passes==3 and beta_guard
decision='P358_ANTIBETA_MARKET_NEUTRAL_PREMIUM_CANDIDATE_SUPPORTED' if supported else 'P358_ANTIBETA_MARKET_NEUTRAL_PREMIUM_NOT_SUPPORTED'
res={'schema':'research.p358_antibeta_market_neutral_r1','parent':'ANTI_BETA_MARKET_NEUTRAL_PREMIUM','claim':'Fresh market-neutral alternative-return-source discriminator using fixed BTAL anti-beta exposure versus BIL cash opportunity control, with SPY used only for opportunity context and realized-beta verification. No fund, cost, date, factor, hedge ratio, window, or allocation search.','contract':{'fund':FUND,'matched_capital_control':'BIL','opportunity_control':'SPY','endpoint_cost_bps':COST_BP,'windows':WINDOWS,'gate':'positive excess CAGR versus BIL and >=3/5 positive chronology folds in all fixed windows, with |realized SPY beta| <= 0.5 in every window'},'results':rows,'window_pass_count':passes,'beta_guard_pass':beta_guard,'decision':decision,'scientific_consequence':'A pass supports one investable anti-beta market-neutral candidate requiring independent representation validation. Failure rejects this fixed formulation without factor, fund, hedge-ratio, cost, or window rescue and rotates to another architecture.','limitations':['single anti-beta fund representation','Yahoo adjusted-price representation','BIL is a capital opportunity control rather than a holdings-matched synthetic benchmark','fund expense ratio and internal trading frictions are embedded only insofar as reflected in adjusted returns'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p358_antibeta_market_neutral_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps(res,sort_keys=True))
