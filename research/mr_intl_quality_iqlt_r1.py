from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/mr_intl_quality_iqlt_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
T=['IQLT','IEFA','SPY']; START='2016-01-01'; COST=.0025
raw=yf.download(T,start=START,auto_adjust=True,progress=False,threads=False); close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw; close=close.dropna(how='all'); rets=close.pct_change().dropna()
def perf(s):
 s=s.dropna(); eq=(1+s).cumprod(); years=len(s)/252; return {'cagr':float(eq.iloc[-1]**(1/years)-1),'max_drawdown':float((eq/eq.cummax()-1).min()),'vol':float(s.std()*np.sqrt(252))}
def ac(t):
 s=rets[t].dropna(); return (float((1+s).prod())*(1-COST))**(1/(len(s)/252))-1
annual=[]
for y,g in close.groupby(close.index.year):
 if y<2017: continue
 r={'year':int(y)}
 for t in T:
  s=g[t].dropna(); r[t]=None if len(s)<100 else float(s.iloc[-1]/s.iloc[0]-1-COST)
 if r['IQLT'] is not None and r['IEFA'] is not None:r['excess_vs_iefa']=r['IQLT']-r['IEFA']
 annual.append(r)
p={t:perf(rets[t]) for t in T}; c={t:ac(t) for t in T}; e=[r for r in annual if r.get('excess_vs_iefa') is not None]; pos=sum(r['excess_vs_iefa']>0 for r in e); recent=[r for r in e if r['year']>=2022]; rx=float(np.mean([r['excess_vs_iefa'] for r in recent])) if recent else None; ex=c['IQLT']-c['IEFA']
support=ex>.01 and len(e)>=9 and pos>=int(np.ceil(len(e)*.6)) and rx is not None and rx>0 and p['IQLT']['max_drawdown']>=p['IEFA']['max_drawdown']-.05
decision='INTERNATIONAL_QUALITY_ALPHA_SUPPORTED' if support else 'INTERNATIONAL_QUALITY_ALPHA_NOT_SUPPORTED'
out={'schema':'research.mr_intl_quality_iqlt_r1.v1','workload_id':'MR_INTL_QUALITY_IQLT_R1','claim':'Test whether developed-ex-US quality selection delivers durable after-cost excess over a matched developed-ex-US control.','contract':{'candidate':'IQLT','matched_region_control':'IEFA','broad_us_reference':'SPY','start':START,'entry_cost_bps':25,'support_rule':'>1 pp CAGR excess vs IEFA; >=60% positive eligible calendar folds with >=9 folds; positive 2022+ mean excess; max drawdown no worse by >5 pp; no rescue'},'performance':p,'after_cost_cagr':c,'excess_cagr_vs_iefa':ex,'positive_excess_years':pos,'eligible_years':len(e),'post_2022_mean_excess_vs_iefa':rx,'annual':annual,'decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'after_cost_cagr':c,'excess_vs_iefa':ex,'positive_years':pos,'eligible_years':len(e),'post_2022_mean_excess_vs_iefa':rx,'max_dd':{t:p[t]['max_drawdown'] for t in T}},sort_keys=True))