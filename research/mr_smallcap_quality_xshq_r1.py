from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/mr_smallcap_quality_xshq_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
T=['XSHQ','IWM','SPY']; START='2018-01-01'; COST=.0025
raw=yf.download(T,start=START,auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
close=close.dropna(how='all')
rets=close.pct_change().dropna()
def perf(s):
 s=s.dropna(); eq=(1+s).cumprod(); years=len(s)/252; cagr=float(eq.iloc[-1]**(1/years)-1); peak=eq.cummax(); dd=float((eq/peak-1).min()); vol=float(s.std()*np.sqrt(252)); sharpe=float(s.mean()/s.std()*np.sqrt(252)) if s.std()>0 else None; return {'cagr':cagr,'max_drawdown':dd,'vol':vol,'sharpe':sharpe}
# One-time entry friction is conservative for buy-and-hold implementation comparison.
series={t:rets[t].copy() for t in T}
# Apply fixed entry cost once by reducing first-period wealth equivalently.
def after_cost_cagr(t):
 s=series[t]; eq=(1+s).cumprod(); eq.iloc[0]*=(1-COST); eq=eq/eq.iloc[0]*(1-COST); years=len(s)/252; return float(eq.iloc[-1]**(1/years)-1)
annual=[]
for y,g in close.groupby(close.index.year):
 if y<2019 or y>2026: continue
 row={'year':int(y)}
 for t in T:
  s=g[t].dropna(); row[t]=None if len(s)<100 else float(s.iloc[-1]/s.iloc[0]-1-COST)
 if row['XSHQ'] is not None and row['IWM'] is not None:
  row['excess_vs_iwm']=row['XSHQ']-row['IWM']; row['excess_vs_spy']=None if row['SPY'] is None else row['XSHQ']-row['SPY']
 annual.append(row)
p={t:perf(series[t]) for t in T}; c={t:after_cost_cagr(t) for t in T}; pos=sum(r.get('excess_vs_iwm',0)>0 for r in annual if r.get('excess_vs_iwm') is not None); n=sum(r.get('excess_vs_iwm') is not None for r in annual)
post22=[r for r in annual if r['year']>=2022 and r.get('excess_vs_iwm') is not None]; post22_ex=float(np.mean([r['excess_vs_iwm'] for r in post22])) if post22 else None
ex=c['XSHQ']-c['IWM']; support=(ex>0.01 and n>=6 and pos>=int(np.ceil(n*2/3)) and p['XSHQ']['max_drawdown']>=p['IWM']['max_drawdown']-0.05 and (post22_ex is not None and post22_ex>0))
decision='SMALL_CAP_QUALITY_ALPHA_SUPPORTED' if support else 'SMALL_CAP_QUALITY_ALPHA_NOT_SUPPORTED'
out={'schema':'research.mr_smallcap_quality_xshq_r1.v1','workload_id':'MR_SMALLCAP_QUALITY_XSHQ_R1','claim':'Test whether a transparent small-cap quality fund implementation delivers durable after-cost excess return versus the matched small-cap benchmark rather than merely broad-market beta.','contract':{'candidate':'XSHQ','matched_underlying':'IWM','broad_market':'SPY','start':START,'entry_cost_bps':25,'support_rule':'>1 pp CAGR excess vs IWM; >=2/3 positive calendar-year excess folds with >=6 folds; max drawdown no worse than IWM by >5 pp; positive mean excess from 2022 onward; no rescue'},'performance':p,'after_cost_cagr':c,'after_cost_excess_cagr_vs_iwm':ex,'annual':annual,'positive_iwm_excess_years':pos,'eligible_years':n,'post_2022_mean_excess_vs_iwm':post22_ex,'decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'after_cost_cagr':c,'excess_vs_iwm':ex,'positive_years':pos,'eligible_years':n,'post_2022_mean_excess_vs_iwm':post22_ex,'max_dd':{t:p[t]['max_drawdown'] for t in T}},sort_keys=True))