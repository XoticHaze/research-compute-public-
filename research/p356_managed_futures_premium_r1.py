from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

FUNDS=['DBMF','KMLM']; CONTROLS=['SPY','BIL']; ALL=FUNDS+CONTROLS
START='2020-01-01'; END='2026-09-10'; COST_BP=10; BETA_LOOKBACK=24
WINDOWS={'2022_plus':'2022-01-01','2023_plus':'2023-01-01','2024_plus':'2024-01-01'}
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna(); r=close.resample('ME').last().pct_change().dropna()

def metrics(q):
    q=pd.Series(q,dtype=float).dropna(); n=len(q); eq=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12)
    return {'months':int(n),'cagr':float(eq.iloc[-1]**(12/n)-1),'maxdd':float((eq/eq.cummax()-1).min()),'sharpe_rf0':float(q.mean()*12/vol) if vol else None}

out={}
for fund in FUNDS:
    fr=r[fund]
    # one-month-lagged rolling beta to SPY from only prior completed months, clipped to [0,1]
    cov=fr.rolling(BETA_LOOKBACK).cov(r.SPY); var=r.SPY.rolling(BETA_LOOKBACK).var(); beta=(cov/var).shift(1).clip(0,1)
    bench=beta*r.SPY+(1-beta)*r.BIL
    x=pd.DataFrame({'fund':fr,'bench':bench,'SPY':r.SPY,'BIL':r.BIL}).dropna()
    if len(x):
        f=COST_BP/10000; x.iloc[0,x.columns.get_loc('fund')]-=f; x.iloc[-1,x.columns.get_loc('fund')]-=f
    rows={}
    for name,start in WINDOWS.items():
        q=x.loc[x.index>=pd.Timestamp(start)]
        a,b,s,c=metrics(q.fund),metrics(q.bench),metrics(q.SPY),metrics(q.BIL)
        folds=[]
        for i,ix in enumerate(np.array_split(np.arange(len(q)),5),1):
            z=q.iloc[ix]
            if len(z)<2: continue
            folds.append(metrics(z.fund)['cagr']-metrics(z.bench)['cagr'])
        rows[name]={'fund':a,'beta_matched':b,'SPY':s,'BIL':c,'matched_excess_cagr':a['cagr']-b['cagr'],'positive_matched_folds':sum(v>0 for v in folds),'fold_excess_cagr':folds}
    out[fund]=rows
passes={f:sum(v['matched_excess_cagr']>0 and v['positive_matched_folds']>=3 for v in out[f].values()) for f in FUNDS}
peer_corr=float(r[FUNDS].dropna().corr().iloc[0,1])
# Family support requires both materially different managed-futures implementations to clear >=2/3 fixed windows.
supported=all(passes[f]>=2 for f in FUNDS)
decision='P356_MANAGED_FUTURES_PREMIUM_FAMILY_SUPPORTED' if supported else 'P356_MANAGED_FUTURES_PREMIUM_FAMILY_NOT_CONFIRMED'
res={'schema':'research.p356_managed_futures_premium_r1','parent':'MANAGED_FUTURES_ALTERNATIVE_PREMIUM','claim':'Materially distinct alternative-return-source discriminator using DBMF and KMLM against causal one-month-lagged 24-month SPY-beta-matched SPY+BIL controls. No fund, beta-window, clipping, cost, date, allocation, or threshold search.','contract':{'funds':FUNDS,'beta_lookback_months':BETA_LOOKBACK,'beta_clip':[0,1],'matched_control':'lagged beta*SPY + residual BIL','endpoint_cost_bps':COST_BP,'windows':WINDOWS,'gate':'each fund positive matched excess and >=3/5 positive chronology folds in >=2/3 fixed windows'},'results':out,'fund_window_pass_counts':passes,'peer_return_corr':peer_corr,'decision':decision,'scientific_consequence':'Support requires replication across both fund implementations. Failure closes the broad family claim for this live-history representation without parameter rescue; isolated fund passes remain only implementation-specific evidence.','limitations':['short live fund history, especially KMLM','funds implement different managed-futures methodologies','Yahoo adjusted-price representation','beta-matched benchmark controls equity beta but cannot perfectly match dynamic futures risk exposures'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p356_managed_futures_premium_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))