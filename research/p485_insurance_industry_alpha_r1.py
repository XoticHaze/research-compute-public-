import json, math, os
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT = Path('research/artifacts/p485_insurance_industry_alpha_r1.json')
OUT.parent.mkdir(parents=True, exist_ok=True)
TICKERS = ['KIE','XLF','SPY']
START = '2009-01-01'
END = '2026-09-01'
ENTRY_COST = 0.001

px = yf.download(TICKERS, start=START, end=END, auto_adjust=True, progress=False)['Close']
if isinstance(px, pd.Series):
    px = px.to_frame()
px = px.dropna(how='all').ffill().dropna()
ret = px.pct_change().dropna()

def ann_stats(r):
    n = len(r)
    years = n/252.0
    total = float((1+r).prod())
    cagr = total**(1/years)-1 if years > 0 and total > 0 else float('nan')
    vol = float(r.std(ddof=1)*math.sqrt(252))
    sharpe = float(r.mean()/r.std(ddof=1)*math.sqrt(252)) if r.std(ddof=1)>0 else float('nan')
    wealth=(1+r).cumprod(); dd=wealth/wealth.cummax()-1
    return {'cagr':cagr,'vol':vol,'sharpe':sharpe,'max_drawdown':float(dd.min()),'n':n}

def beta_alpha(y, x):
    y=np.asarray(y,float); x=np.asarray(x,float)
    X=np.column_stack([np.ones(len(x)),x])
    coef=np.linalg.lstsq(X,y,rcond=None)[0]
    return float(coef[1]), float(coef[0]*252)

def window(start):
    r=ret.loc[start:]
    k=ann_stats(r['KIE']); x=ann_stats(r['XLF']); s=ann_stats(r['SPY'])
    beta_x, alpha_x=beta_alpha(r['KIE'],r['XLF'])
    beta_s, alpha_s=beta_alpha(r['KIE'],r['SPY'])
    years=len(r)/252.0
    cost_drag=(1-ENTRY_COST)**(1/years)-1 if years>0 else 0
    k_after=k['cagr']+cost_drag
    return {'start':start,'kie':k,'xlf':x,'spy':s,'kie_after_cost_cagr':k_after,
            'excess_vs_xlf':k_after-x['cagr'],'excess_vs_spy':k_after-s['cagr'],
            'beta_vs_xlf':beta_x,'alpha_vs_xlf_ann':alpha_x,'beta_vs_spy':beta_s,'alpha_vs_spy_ann':alpha_s}

windows=[window(x) for x in ['2010-01-01','2015-01-01','2020-01-01']]
# Four non-overlapping chronology blocks with enough history.
blocks=[]
for a,b in [('2010-01-01','2013-12-31'),('2014-01-01','2017-12-31'),('2018-01-01','2021-12-31'),('2022-01-01','2026-09-01')]:
    r=ret.loc[a:b]
    if len(r)<100: continue
    ky=ann_stats(r['KIE']); xy=ann_stats(r['XLF'])
    beta,alpha=beta_alpha(r['KIE'],r['XLF'])
    years=len(r)/252.0; cost_drag=(1-ENTRY_COST)**(1/years)-1
    ka=ky['cagr']+cost_drag
    blocks.append({'start':a,'end':b,'kie_after_cost_cagr':ka,'xlf_cagr':xy['cagr'],'excess_vs_xlf':ka-xy['cagr'],'alpha_vs_xlf_ann':alpha,'beta_vs_xlf':beta})

pass_windows=all(w['excess_vs_xlf']>0 and w['alpha_vs_xlf_ann']>0 for w in windows)
positive_blocks=sum(1 for b in blocks if b['excess_vs_xlf']>0 and b['alpha_vs_xlf_ann']>0)
decision='INSURANCE_INDUSTRY_ALPHA_SUPPORTED' if pass_windows and positive_blocks>=3 else 'INSURANCE_INDUSTRY_ALPHA_NOT_SUPPORTED'
result={'schema':'research.p485_insurance_industry_alpha_r1.v1','hypothesis':'KIE insurance-industry selection delivers durable after-cost alpha versus matched financial-sector XLF exposure, with SPY as opportunity-cost context.','source':'Yahoo Finance via yfinance; adjusted fund returns; research-only dynamic source','entry_cost':ENTRY_COST,'windows':windows,'chronology_blocks':blocks,'positive_blocks':positive_blocks,'decision':decision,'acceptance':'positive after-cost excess and positive beta-adjusted annual alpha versus XLF in all fixed windows and >=3/4 chronology blocks; no date/product/cost rescue'}
OUT.write_text(json.dumps(result,indent=2,sort_keys=True))
print(json.dumps(result))
