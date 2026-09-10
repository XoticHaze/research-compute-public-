from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

CAND='DLS'; MATCHED='SCZ'; CONTROLS=['SPY','QQQ']; START='2007-01-01'; END='2026-09-10'; COST=10.0
WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.; ann=float(q.mean()*12) if n else 0.
 return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None,'sharpe_rf0':float(ann/vol) if vol else None}
def ep(r):
 q=pd.Series(r,dtype=float).dropna().copy(); f=COST/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def folds(a,b):
 z=pd.DataFrame({'a':a,'b':b}).dropna(); out=[]
 for c in np.array_split(z,5):
  if len(c)>=12: out.append(metric(ep(c.a))['cagr']-metric(ep(c.b))['cagr'])
 return out
raw=yf.download([CAND,MATCHED]+CONTROLS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[[CAND,MATCHED]+CONTROLS].dropna().resample('ME').last(); r=px.pct_change().dropna(); out={}
for name,start in WINDOWS.items():
 z=r.loc[r.index>=pd.Timestamp(start)]; c=metric(ep(z[CAND])); b=metric(ep(z[MATCHED])); f=folds(z[CAND],z[MATCHED]); spy=metric(ep(z.SPY)); qqq=metric(ep(z.QQQ))
 out[name]={'candidate':c,'matched':b,'matched_excess_cagr':c['cagr']-b['cagr'],'positive_matched_folds':sum(x>0 for x in f),'fold_count':len(f),'fold_excess_cagr':f,'vs_SPY_cagr':c['cagr']-spy['cagr'],'vs_QQQ_cagr':c['cagr']-qqq['cagr']}
p=out['2010']; q=out['2020']; s=out['2022']; ok=p['matched_excess_cagr']>0 and p['positive_matched_folds']>=3 and q['matched_excess_cagr']>0 and q['positive_matched_folds']>=3 and s['matched_excess_cagr']>0
res={'schema':'research.p284_intl_smallvalue_transport_r1','parent':'P249/P284','claim':'Test whether the developed ex-US small-value premise embedded in P249 transports to a long-history independent value/dividend-tilted small-cap representation, DLS, against broad developed ex-US small-cap SCZ, without changing P249 or optimizing any rule.','parameters':{'candidate':CAND,'matched':MATCHED,'entry_exit_bps':COST,'windows':WINDOWS,'no_tuning':True},'results':out,'decision_rule':'SUPPORTED_TRANSPORT if DLS has positive matched excess with >=3/5 positive folds in both 2010+ and 2020+, and positive 2022+ matched excess. MIXED if some windows pass; otherwise NOT_SUPPORTED_DIMENSION. This alternate representation cannot by itself kill P249.','decision':'P284_INTL_SMALLVALUE_TRANSPORT_SUPPORTED' if ok else ('P284_INTL_SMALLVALUE_TRANSPORT_MIXED' if any(v['matched_excess_cagr']>0 for v in out.values()) else 'P284_INTL_SMALLVALUE_TRANSPORT_NOT_SUPPORTED_DIMENSION'),'limitations':['DLS dividend weighting is a long-history value proxy, not byte-identical AVDV methodology','SCZ is a broad developed ex-US small-cap control','Yahoo adjusted-price research data','scientific evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p284_intl_smallvalue_transport_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
