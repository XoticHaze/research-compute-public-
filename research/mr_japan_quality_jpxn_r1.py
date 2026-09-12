from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/mr_japan_quality_jpxn_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
T=['JPXN','EWJ','SPY']; START='2016-01-01'; COST=.0025
raw=yf.download(T,start=START,auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
close=close.dropna(how='all'); rets=close.pct_change().dropna()
def stats(s):
 s=s.dropna(); eq=(1+s).cumprod(); years=len(s)/252; return {'cagr':float(eq.iloc[-1]**(1/years)-1),'max_drawdown':float((eq/eq.cummax()-1).min()),'vol':float(s.std()*np.sqrt(252))}
def ac_cagr(t):
 s=rets[t].dropna(); gross=float((1+s).prod())*(1-COST); years=len(s)/252; return gross**(1/years)-1
annual=[]
for y,g in close.groupby(close.index.year):
 if y<2017: continue
 r={'year':int(y)}
 for t in T:
  s=g[t].dropna(); r[t]=None if len(s)<100 else float(s.iloc[-1]/s.iloc[0]-1-COST)
 if r['JPXN'] is not None and r['EWJ'] is not None: r['excess_vs_ewj']=r['JPXN']-r['EWJ']
 annual.append(r)
p={t:stats(rets[t]) for t in T}; c={t:ac_cagr(t) for t in T}; eligible=[r for r in annual if r.get('excess_vs_ewj') is not None]; pos=sum(r['excess_vs_ewj']>0 for r in eligible); recent=[r for r in eligible if r['year']>=2022]; recent_ex=float(np.mean([r['excess_vs_ewj'] for r in recent])) if recent else None
ex=c['JPXN']-c['EWJ']; support=ex>.01 and len(eligible)>=8 and pos>=int(np.ceil(len(eligible)*.6)) and recent_ex is not None and recent_ex>0 and p['JPXN']['max_drawdown']>=p['EWJ']['max_drawdown']-.05
decision='JAPAN_QUALITY_INDEX_ALPHA_SUPPORTED' if support else 'JAPAN_QUALITY_INDEX_ALPHA_NOT_SUPPORTED'
out={'schema':'research.mr_japan_quality_jpxn_r1.v1','workload_id':'MR_JAPAN_QUALITY_JPXN_R1','claim':'Test whether the JPX-Nikkei 400 quality/capital-efficiency selection implementation delivers durable after-cost excess versus a broad Japan equity control, rather than merely Japan beta.','contract':{'candidate':'JPXN','matched_country_control':'EWJ','broad_market_reference':'SPY','start':START,'entry_cost_bps':25,'support_rule':'>1 pp CAGR excess vs EWJ; >=60% positive eligible calendar folds with >=8 folds; positive mean excess from 2022 onward; max drawdown no worse than EWJ by >5 pp; no rescue'},'performance':p,'after_cost_cagr':c,'excess_cagr_vs_ewj':ex,'positive_excess_years':pos,'eligible_years':len(eligible),'post_2022_mean_excess_vs_ewj':recent_ex,'annual':annual,'decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'after_cost_cagr':c,'excess_vs_ewj':ex,'positive_years':pos,'eligible_years':len(eligible),'post_2022_mean_excess_vs_ewj':recent_ex,'max_dd':{t:p[t]['max_drawdown'] for t in T}},sort_keys=True))