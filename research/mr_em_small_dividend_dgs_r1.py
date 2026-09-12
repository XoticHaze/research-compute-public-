from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/mr_em_small_dividend_dgs_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
T=['DGS','EEMS','VWO']; START='2012-01-01'; COST=.0025
raw=yf.download(T,start=START,auto_adjust=True,progress=False,threads=False)
close=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw; close=close.dropna(how='all'); rets=close.pct_change().dropna()
def perf(s):
 s=s.dropna(); eq=(1+s).cumprod(); years=len(s)/252; return {'cagr':float(eq.iloc[-1]**(1/years)-1),'max_drawdown':float((eq/eq.cummax()-1).min()),'vol':float(s.std()*np.sqrt(252))}
def cagr(t):
 s=rets[t].dropna(); return (float((1+s).prod())*(1-COST))**(1/(len(s)/252))-1
annual=[]
for y,g in close.groupby(close.index.year):
 if y<2013: continue
 r={'year':int(y)}
 for t in T:
  s=g[t].dropna(); r[t]=None if len(s)<100 else float(s.iloc[-1]/s.iloc[0]-1-COST)
 if r['DGS'] is not None and r['EEMS'] is not None:r['excess_vs_eems']=r['DGS']-r['EEMS']
 annual.append(r)
p={t:perf(rets[t]) for t in T}; c={t:cagr(t) for t in T}; e=[r for r in annual if r.get('excess_vs_eems') is not None]; pos=sum(r['excess_vs_eems']>0 for r in e); recent=[r for r in e if r['year']>=2022]; rx=float(np.mean([r['excess_vs_eems'] for r in recent])) if recent else None; ex=c['DGS']-c['EEMS']
support=ex>.01 and len(e)>=10 and pos>=int(np.ceil(len(e)*.6)) and rx is not None and rx>0 and p['DGS']['max_drawdown']>=p['EEMS']['max_drawdown']-.05
decision='EM_SMALL_DIVIDEND_ALPHA_SUPPORTED' if support else 'EM_SMALL_DIVIDEND_ALPHA_NOT_SUPPORTED'
out={'schema':'research.mr_em_small_dividend_dgs_r1.v1','workload_id':'MR_EM_SMALL_DIVIDEND_DGS_R1','claim':'Test whether emerging-market small-cap dividend/value selection delivers durable after-cost excess over a matched emerging-small-cap control.','contract':{'candidate':'DGS','matched_size_region_control':'EEMS','broad_em_reference':'VWO','start':START,'entry_cost_bps':25,'support_rule':'>1 pp CAGR excess vs EEMS; >=60% positive eligible calendar folds with >=10 folds; positive 2022+ mean excess; max drawdown no worse than EEMS by >5 pp; no rescue'},'performance':p,'after_cost_cagr':c,'excess_cagr_vs_eems':ex,'positive_excess_years':pos,'eligible_years':len(e),'post_2022_mean_excess_vs_eems':rx,'annual':annual,'decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'after_cost_cagr':c,'excess_vs_eems':ex,'positive_years':pos,'eligible_years':len(e),'post_2022_mean_excess_vs_eems':rx,'max_dd':{t:p[t]['max_drawdown'] for t in T}},sort_keys=True))