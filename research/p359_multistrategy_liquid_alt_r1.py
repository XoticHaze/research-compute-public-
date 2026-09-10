from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

FUND='QAI'; CONTROLS=['SPY','BIL']; ALL=[FUND]+CONTROLS
START='2009-01-01'; END='2026-09-10'; COST_BP=10; BETA_LOOKBACK=24
WINDOWS={'2012_plus':'2012-01-01','2018_plus':'2018-01-01','2020_plus':'2020-01-01'}
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna(); r=close.resample('ME').last().pct_change().dropna()

def metrics(q):
    q=pd.Series(q,dtype=float).dropna(); n=len(q)
    if n<2: return {'months':int(n),'cagr':None,'maxdd':None,'sharpe_rf0':None}
    eq=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12)
    return {'months':int(n),'cagr':float(eq.iloc[-1]**(12/n)-1),'maxdd':float((eq/eq.cummax()-1).min()),'sharpe_rf0':float(q.mean()*12/vol) if vol else None}

fr=r[FUND]; cov=fr.rolling(BETA_LOOKBACK).cov(r.SPY); var=r.SPY.rolling(BETA_LOOKBACK).var(); beta=(cov/var).shift(1).clip(0,1)
bench=beta*r.SPY+(1-beta)*r.BIL
x=pd.DataFrame({'fund':fr,'bench':bench,'SPY':r.SPY,'BIL':r.BIL,'beta':beta}).dropna()
if len(x):
    f=COST_BP/10000; x.iloc[0,x.columns.get_loc('fund')]-=f; x.iloc[-1,x.columns.get_loc('fund')]-=f
rows={}
for name,start in WINDOWS.items():
    q=x.loc[x.index>=pd.Timestamp(start)]
    a,b,s,c=metrics(q.fund),metrics(q.bench),metrics(q.SPY),metrics(q.BIL)
    folds=[]
    for ix in np.array_split(np.arange(len(q)),5):
        z=q.iloc[ix]
        if len(z)<2: continue
        folds.append(metrics(z.fund)['cagr']-metrics(z.bench)['cagr'])
    rows[name]={'fund':a,'beta_matched':b,'SPY':s,'BIL':c,'matched_excess_cagr':a['cagr']-b['cagr'],'vs_SPY_cagr':a['cagr']-s['cagr'],'positive_matched_folds':sum(v>0 for v in folds),'fold_excess_cagr':folds,'mean_lagged_beta':float(q.beta.mean())}
passes=sum(v['matched_excess_cagr']>0 and v['positive_matched_folds']>=3 for v in rows.values())
dd_guard=all(v['fund']['maxdd'] >= v['beta_matched']['maxdd']-0.05 for v in rows.values())
supported=passes==3 and dd_guard
decision='P359_MULTISTRATEGY_LIQUID_ALT_CANDIDATE_SUPPORTED' if supported else 'P359_MULTISTRATEGY_LIQUID_ALT_NOT_SUPPORTED'
res={'schema':'research.p359_multistrategy_liquid_alt_r1','parent':'MULTISTRATEGY_LIQUID_ALTERNATIVE_PREMIUM','claim':'Fresh diversified liquid-alternative discriminator using fixed QAI exposure versus a causal one-month-lagged 24-month SPY-beta-matched SPY+BIL control. No fund, beta-window, clipping, cost, date, allocation, threshold, component, or hedge-ratio search.','contract':{'fund':FUND,'beta_lookback_months':BETA_LOOKBACK,'beta_clip':[0,1],'matched_control':'lagged beta*SPY + residual BIL','endpoint_cost_bps':COST_BP,'windows':WINDOWS,'gate':'positive matched excess and >=3/5 positive chronology folds in all three fixed windows, with fund max drawdown no worse than beta-matched control by >5pp'},'results':rows,'window_pass_count':passes,'drawdown_guard_pass':dd_guard,'decision':decision,'scientific_consequence':'A pass supports one multi-strategy liquid-alternative candidate requiring independent representation validation. Failure rejects this formulation without fund, component, beta, cost, or window rescue and rotates to another architecture.','limitations':['single diversified liquid-alternative fund representation','Yahoo adjusted-price representation','beta-matched benchmark controls broad equity beta but not the fund components or embedded dynamic hedges'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p359_multistrategy_liquid_alt_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps(res,sort_keys=True))
