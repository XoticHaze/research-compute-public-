from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

PAIRS={'IJS_vs_IJR':('IJS','IJR'),'VBR_vs_VB':('VBR','VB')}; CONTROLS=['SPY','QQQ']; START='2004-01-01'; END='2026-09-10'; ENTRY_EXIT_BPS=10.0
WINDOWS={'2007':'2007-01-01','2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.; ann=float(q.mean()*12) if n else 0.
 return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None,'sharpe_rf0':float(ann/vol) if vol else None}
def endpoint_cost(r,bps):
 q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def folds(a,b):
 z=pd.DataFrame({'a':a,'b':b}).dropna(); out=[]
 for c in np.array_split(z,5):
  if len(c)>=12: out.append(metric(endpoint_cost(c.a,ENTRY_EXIT_BPS))['cagr']-metric(endpoint_cost(c.b,ENTRY_EXIT_BPS))['cagr'])
 return out
syms=sorted(set(sum(([a,b] for a,b in PAIRS.values()),[])+CONTROLS)); raw=yf.download(syms,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[syms].dropna().resample('ME').last(); ret=px.pct_change().dropna(); results={}
for w,start in WINDOWS.items():
 z=ret.loc[ret.index>=pd.Timestamp(start)]; wr={}
 for name,(cand,base) in PAIRS.items():
  c=endpoint_cost(z[cand],ENTRY_EXIT_BPS); b=endpoint_cost(z[base],ENTRY_EXIT_BPS); cm=metric(c); bm=metric(b); f=folds(z[cand],z[base])
  wr[name]={'candidate':cand,'matched':base,'candidate_metrics':cm,'matched_metrics':bm,'matched_excess_cagr':cm['cagr']-bm['cagr'],'positive_matched_folds':sum(x>0 for x in f),'fold_count':len(f),'fold_excess_cagr':f,'vs_SPY_cagr':cm['cagr']-metric(endpoint_cost(z.SPY,ENTRY_EXIT_BPS))['cagr'],'vs_QQQ_cagr':cm['cagr']-metric(endpoint_cost(z.QQQ,ENTRY_EXIT_BPS))['cagr']}
 results[w]=wr
p=results['2010']; q=results['2020']; longpass=all(p[k]['matched_excess_cagr']>0 and p[k]['positive_matched_folds']>=3 for k in PAIRS); recent=sum(q[k]['matched_excess_cagr']>0 for k in PAIRS)
if longpass and recent==2: decision='P283_US_SMALLVALUE_TRANSPORT_SUPPORTED'
elif longpass or recent>=1: decision='P283_US_SMALLVALUE_TRANSPORT_MIXED'
else: decision='P283_US_SMALLVALUE_TRANSPORT_NOT_SUPPORTED_DIMENSION'
out={'schema':'research.p283_us_smallvalue_transport_r1','parent':'P249/P283','claim':'Test whether the US small-value premise embedded in P249 transports beyond AVUV using two independent long-history passive implementations, IJS versus IJR and VBR versus VB, without altering P249 or optimizing any rule.','parameters':{'pairs':PAIRS,'entry_exit_bps':ENTRY_EXIT_BPS,'windows':WINDOWS,'no_tuning':True},'results':results,'decision_rule':'SUPPORTED if both independent small-value representations have positive matched excess with >=3/5 positive chronology folds in 2010+ and both remain positive in 2020+. MIXED if long-history transport is common or at least one representation remains positive recently. Otherwise NOT_SUPPORTED_DIMENSION. This adjudicates only US small-value representation robustness and cannot kill P249 by itself.','decision':decision,'limitations':['Yahoo adjusted-price public research data','IJS and VBR are independent US small-value/value implementations, not byte-identical AVUV semantics','does not adjudicate P249 international small-value component','scientific evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p283_us_smallvalue_transport_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
