from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

FUND='QYLD'; CONTROLS=['QQQ','BIL']; ALL=[FUND]+CONTROLS
START='2013-01-01'; END='2026-09-10'; COST_BP=10; LOOKBACK=24
WINDOWS={'2015_plus':'2015-01-01','2018_plus':'2018-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna(); r=close.resample('ME').last().pct_change().dropna()
def metrics(q):
    q=pd.Series(q,dtype=float).dropna(); n=len(q)
    if n<2:return {'months':int(n),'cagr':None,'maxdd':None,'sharpe_rf0':None}
    eq=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12)
    return {'months':int(n),'cagr':float(eq.iloc[-1]**(12/n)-1),'maxdd':float((eq/eq.cummax()-1).min()),'sharpe_rf0':float(q.mean()*12/vol) if vol else None}
fr=r[FUND]; beta=(fr.rolling(LOOKBACK).cov(r.QQQ)/r.QQQ.rolling(LOOKBACK).var()).shift(1).clip(0,1); bench=beta*r.QQQ+(1-beta)*r.BIL
x=pd.DataFrame({'fund':fr,'bench':bench,'QQQ':r.QQQ,'BIL':r.BIL,'beta':beta}).dropna()
if len(x):
    f=COST_BP/10000; x.iloc[0,x.columns.get_loc('fund')]-=f; x.iloc[-1,x.columns.get_loc('fund')]-=f
rows={}
for name,start in WINDOWS.items():
    q=x.loc[x.index>=pd.Timestamp(start)]; a,b,c,d=metrics(q.fund),metrics(q.bench),metrics(q.QQQ),metrics(q.BIL)
    folds=[]
    for ix in np.array_split(np.arange(len(q)),5):
        z=q.iloc[ix]
        if len(z)>=2: folds.append(metrics(z.fund)['cagr']-metrics(z.bench)['cagr'])
    rows[name]={'fund':a,'matched':b,'QQQ':c,'BIL':d,'matched_excess_cagr':a['cagr']-b['cagr'],'vs_QQQ_cagr':a['cagr']-c['cagr'],'positive_matched_folds':sum(v>0 for v in folds),'fold_excess_cagr':folds,'mean_lagged_beta':float(q.beta.mean())}
passes=sum(v['matched_excess_cagr']>0 and v['positive_matched_folds']>=3 for v in rows.values()); dd_guard=all(v['fund']['maxdd']>=v['matched']['maxdd']-0.05 for v in rows.values()); supported=passes==len(WINDOWS) and dd_guard
decision='P364_COVERED_CALL_PREMIUM_SUPPORTED' if supported else 'P364_COVERED_CALL_PREMIUM_NOT_SUPPORTED'
res={'schema':'research.p364_covered_call_premium_r1','parent':'COVERED_CALL_OPTION_PREMIUM','claim':'Orthogonal option-income discriminator using fixed QYLD versus causal lagged 24-month QQQ-beta-matched QQQ+BIL control. No fund, beta-window, clipping, cost, date, allocation, threshold or window search.','contract':{'fund':FUND,'matched_control':'lagged beta*QQQ + residual BIL','endpoint_cost_bps':COST_BP,'windows':WINDOWS,'gate':'positive matched excess and >=3/5 positive chronology folds in every fixed window, drawdown no worse than matched by >5pp'},'results':rows,'window_pass_count':passes,'drawdown_guard_pass':dd_guard,'decision':decision,'scientific_consequence':'Pass supports a covered-call premium candidate requiring independent representation validation. Failure rejects the fixed formulation without fund/beta/cost/window rescue and rotates architecture.','limitations':['single QYLD implementation','Yahoo adjusted-price representation includes distributions','beta control does not explicitly replicate option strike/path dependence or tax treatment'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p364_covered_call_premium_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
