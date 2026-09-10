from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
CAND='XMMO'; BASE='IJH'; START='2014-01-01'; END='2026-09-10'; COSTS=[10,25,50]; WINDOWS={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None}
def ep(r,bps):
 q=pd.Series(r,dtype=float).dropna().copy(); f=bps/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def folds(a,b,bps):
 z=pd.DataFrame({'a':a,'b':b}).dropna(); out=[]
 for pos in np.array_split(np.arange(len(z)),5):
  c=z.iloc[pos]
  if len(c)>=12: out.append(metric(ep(c.a,bps))['cagr']-metric(ep(c.b,bps))['cagr'])
 return out
raw=yf.download([CAND,BASE],start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[[CAND,BASE]].dropna().resample('ME').last(); r=px.pct_change().dropna(); results={}
for bps in COSTS:
 cr={}
 for n,start in WINDOWS.items():
  z=r.loc[r.index>=pd.Timestamp(start)]; cm=metric(ep(z[CAND],bps)); bm=metric(ep(z[BASE],bps)); f=folds(z[CAND],z[BASE],bps); cr[n]={'candidate':cm,'matched':bm,'matched_excess_cagr':cm['cagr']-bm['cagr'],'positive_matched_folds':sum(x>0 for x in f),'fold_count':len(f)}
 results[str(bps)]=cr
ok=all(results[str(c)][w]['matched_excess_cagr']>0 for c in COSTS for w in WINDOWS) and all(results[str(c)]['2015']['positive_matched_folds']>=3 for c in COSTS)
out={'schema':'research.p299_midcap_momentum_cost_r1','parent':'P299/P297/P298','claim':'Test whether independently confirmed XMMO-vs-IJH mid-cap momentum excess remains robust when fixed endpoint costs rise from 10 to 25 and 50 bps, with no product, window, or parameter changes.','parameters':{'candidate':CAND,'matched':BASE,'endpoint_cost_bps':COSTS,'windows':WINDOWS,'no_search':True},'results':results,'decision_rule':'Cost robustness requires positive matched excess in 2015+, 2020+, and 2022+ at every cost level and >=3/5 positive 2015+ chronology folds at every cost level.','decision':'P299_XMMO_COST_ROBUST' if ok else 'P299_XMMO_COST_SENSITIVITY','limitations':['endpoint transaction-cost stress is conservative implementation friction, not observed ETF slippage','same adjusted-price provider as P297/P298','scientific evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p299_midcap_momentum_cost_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
