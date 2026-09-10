from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
PAIRS={'QUAL_vs_IWB':('QUAL','IWB'),'SPHQ_vs_SPY':('SPHQ','SPY')}; CONTROL='QQQ'; START='2013-01-01'; END='2026-09-10'; COST=10.0; WINDOWS={'2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}
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
syms=sorted(set(sum(([a,b] for a,b in PAIRS.values()),[])+[CONTROL])); raw=yf.download(syms,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[syms].dropna().resample('ME').last(); r=px.pct_change().dropna(); results={}
for w,start in WINDOWS.items():
 z=r.loc[r.index>=pd.Timestamp(start)]; wr={}
 for name,(cand,base) in PAIRS.items():
  cm=metric(ep(z[cand])); bm=metric(ep(z[base])); fm=folds(z[cand],z[base]); q=metric(ep(z[CONTROL])); wr[name]={'candidate':cand,'matched':base,'candidate_metrics':cm,'matched_metrics':bm,'matched_excess_cagr':cm['cagr']-bm['cagr'],'positive_matched_folds':sum(x>0 for x in fm),'fold_count':len(fm),'fold_excess_cagr':fm,'vs_QQQ_cagr':cm['cagr']-q['cagr']}
 results[w]=wr
p=results['2015']; q=results['2020']; s=results['2022']; ok=all(p[k]['matched_excess_cagr']>0 and p[k]['positive_matched_folds']>=3 and p[k]['candidate_metrics']['maxdd']>=p[k]['matched_metrics']['maxdd']-.05 for k in PAIRS) and all(q[k]['matched_excess_cagr']>0 for k in PAIRS) and any(s[k]['matched_excess_cagr']>0 for k in PAIRS)
res={'schema':'research.p285_quality_factor_r1','parent':'P285','claim':'Two independent investable US quality-factor implementations earn persistent after-cost excess versus matched broad-universe controls without timing, selection, or weight optimization.','parameters':{'pairs':PAIRS,'entry_exit_bps':COST,'windows':WINDOWS,'no_tuning':True},'results':results,'decision_rule':'SUPPORTED_CANDIDATE if both matched pairs have positive 2015+ excess with >=3/5 positive chronology folds and no >5pp drawdown penalty, both remain positive 2020+, and at least one remains positive 2022+. Otherwise classify mixed or not supported without product/window tuning. QQQ is opportunity context, not matched gate.','decision':'P285_QUALITY_FACTOR_SUPPORTED_CANDIDATE' if ok else ('P285_QUALITY_FACTOR_MIXED' if any(v['matched_excess_cagr']>0 for w in results.values() for v in w.values()) else 'P285_QUALITY_FACTOR_NOT_SUPPORTED'),'limitations':['ETF methodologies and fees are embedded in adjusted returns','QUAL history begins 2013','scientific evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p285_quality_factor_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(res,sort_keys=True))
