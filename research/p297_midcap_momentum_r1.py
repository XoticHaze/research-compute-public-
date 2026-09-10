from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
CAND='XMMO'; BASE='IJH'; US='SPY'; GROWTH='QQQ'; START='2014-01-01'; END='2026-09-10'; COST=10/10000; WINDOWS={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.; return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None,'sharpe_rf0':float(q.mean()*12/vol) if vol else None}
def ep(r):
 q=pd.Series(r,dtype=float).dropna().copy()
 if len(q): q.iloc[0]-=COST; q.iloc[-1]-=COST
 return q
def folds(a,b):
 z=pd.DataFrame({'a':a,'b':b}).dropna(); out=[]
 for pos in np.array_split(np.arange(len(z)),5):
  c=z.iloc[pos]
  if len(c)>=12: out.append(metric(ep(c.a))['cagr']-metric(ep(c.b))['cagr'])
 return out
syms=[CAND,BASE,US,GROWTH]; raw=yf.download(syms,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[syms].dropna().resample('ME').last(); r=px.pct_change().dropna(); results={}
for n,start in WINDOWS.items():
 z=r.loc[r.index>=pd.Timestamp(start)]; cm=metric(ep(z[CAND])); bm=metric(ep(z[BASE])); sm=metric(ep(z[US])); qm=metric(ep(z[GROWTH])); f=folds(z[CAND],z[BASE]); results[n]={'candidate':cm,'matched':bm,'matched_excess_cagr':cm['cagr']-bm['cagr'],'positive_matched_folds':sum(x>0 for x in f),'fold_count':len(f),'fold_excess_cagr':f,'vs_SPY_cagr':cm['cagr']-sm['cagr'],'vs_QQQ_cagr':cm['cagr']-qm['cagr']}
p=results['2015']; q=results['2020']; s=results['2022']; ok=p['matched_excess_cagr']>0 and p['positive_matched_folds']>=3 and p['candidate']['maxdd']>=p['matched']['maxdd']-.05 and q['matched_excess_cagr']>0 and s['matched_excess_cagr']>0
out={'schema':'research.p297_midcap_momentum_r1','parent':'P297','claim':'Test whether an investable U.S. mid-cap momentum implementation transports the supported stock-momentum idea by earning persistent after-cost excess versus a matched broad mid-cap control, without changing SPMO or searching momentum parameters.','parameters':{'candidate':CAND,'matched':BASE,'endpoint_cost_bps':10,'windows':WINDOWS,'no_product_parameter_window_search':True},'results':results,'decision_rule':'Transport support requires positive 2015+ matched excess, >=3/5 positive chronology folds, no >5pp drawdown penalty, and positive matched excess in both 2020+ and 2022+. SPY/QQQ are opportunity context only.','decision':'P297_MIDCAP_MOMENTUM_TRANSPORT_SUPPORTED' if ok else 'P297_MIDCAP_MOMENTUM_TRANSPORT_NOT_SUPPORTED','limitations':['fund/index methodology and fees embedded in adjusted returns','single fixed investable mid-cap implementation; failure does not invalidate SPMO','scientific evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p297_midcap_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
