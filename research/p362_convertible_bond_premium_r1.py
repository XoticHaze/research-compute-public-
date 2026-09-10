from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

FUND='CWB'; CONTROLS=['SPY','IEF']; ALL=[FUND]+CONTROLS
START='2009-01-01'; END='2026-09-10'; COST_BP=10; LOOKBACK=24
WINDOWS={'2012_plus':'2012-01-01','2018_plus':'2018-01-01','2020_plus':'2020-01-01'}
raw=yf.download(ALL,start=START,end=END,auto_adjust=True,progress=False,threads=False)
close=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ALL].dropna(); r=close.resample('ME').last().pct_change().dropna()

def metrics(q):
    q=pd.Series(q,dtype=float).dropna(); n=len(q)
    if n<2: return {'months':int(n),'cagr':None,'maxdd':None,'sharpe_rf0':None}
    eq=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12)
    return {'months':int(n),'cagr':float(eq.iloc[-1]**(12/n)-1),'maxdd':float((eq/eq.cummax()-1).min()),'sharpe_rf0':float(q.mean()*12/vol) if vol else None}

fr=r[FUND]
# Prospectively fixed causal two-asset matched control. Estimate prior 24m OLS exposures to SPY and IEF, lag one month, clip each [0,1], normalize only if sum > 1; residual is zero-return cash.
X=pd.DataFrame({'SPY':r.SPY,'IEF':r.IEF})
betas=[]
for i in range(len(r)):
    if i<LOOKBACK: betas.append((np.nan,np.nan)); continue
    y=fr.iloc[i-LOOKBACK:i].values; x=X.iloc[i-LOOKBACK:i].values
    b=np.linalg.lstsq(x,y,rcond=None)[0]; b=np.clip(b,0,1)
    if b.sum()>1: b=b/b.sum()
    betas.append((float(b[0]),float(b[1])))
b=pd.DataFrame(betas,index=r.index,columns=['b_spy','b_ief']).shift(1)
bench=b.b_spy*r.SPY+b.b_ief*r.IEF
x=pd.concat([fr.rename('fund'),bench.rename('bench'),r.SPY,r.IEF,b],axis=1).dropna()
if len(x):
    f=COST_BP/10000; x.iloc[0,x.columns.get_loc('fund')]-=f; x.iloc[-1,x.columns.get_loc('fund')]-=f
rows={}
for name,start in WINDOWS.items():
    q=x.loc[x.index>=pd.Timestamp(start)]
    a,c,s,i=metrics(q.fund),metrics(q.bench),metrics(q.SPY),metrics(q.IEF)
    folds=[]
    for ix in np.array_split(np.arange(len(q)),5):
        z=q.iloc[ix]
        if len(z)<2: continue
        folds.append(metrics(z.fund)['cagr']-metrics(z.bench)['cagr'])
    rows[name]={'fund':a,'matched':c,'SPY':s,'IEF':i,'matched_excess_cagr':a['cagr']-c['cagr'],'vs_SPY_cagr':a['cagr']-s['cagr'],'positive_matched_folds':sum(v>0 for v in folds),'fold_excess_cagr':folds,'mean_spy_beta':float(q.b_spy.mean()),'mean_ief_beta':float(q.b_ief.mean())}
passes=sum(v['matched_excess_cagr']>0 and v['positive_matched_folds']>=3 for v in rows.values())
dd_guard=all(v['fund']['maxdd']>=v['matched']['maxdd']-0.05 for v in rows.values())
supported=passes==3 and dd_guard
decision='P362_CONVERTIBLE_BOND_PREMIUM_SUPPORTED' if supported else 'P362_CONVERTIBLE_BOND_PREMIUM_NOT_SUPPORTED'
res={'schema':'research.p362_convertible_bond_premium_r1','parent':'CONVERTIBLE_BOND_HYBRID_PREMIUM','claim':'Materially orthogonal hybrid-capital fund discriminator using fixed CWB convertible-bond exposure versus a causal lagged 24-month SPY+IEF return-matched control. No fund, beta-window, clipping, cost, date, allocation, threshold or window search.','contract':{'fund':FUND,'matched_control':'lagged 24m OLS SPY+IEF betas clipped [0,1], normalized only when sum>1; residual cash=0','endpoint_cost_bps':COST_BP,'windows':WINDOWS,'gate':'positive matched excess and >=3/5 positive chronology folds in every fixed window, with fund max drawdown no worse than matched by >5pp'},'results':rows,'window_pass_count':passes,'drawdown_guard_pass':dd_guard,'decision':decision,'scientific_consequence':'Pass supports one convertible-bond hybrid-premium candidate requiring independent representation validation. Failure rejects this fixed formulation without fund/beta/cost/window rescue and rotates architecture.','limitations':['single investable CWB representation','Yahoo adjusted-price representation','matched control approximates equity/rate exposure but not issuer credit, convexity, callability or embedded option dynamics'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p362_convertible_bond_premium_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps(res,sort_keys=True))
