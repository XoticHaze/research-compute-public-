from __future__ import annotations
import json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
CAND=['SPMO','CALF']; BASE=['SPY','IJR']; CONTROL='QQQ'; START='2018-01-01'; END='2026-09-10'; COSTS=[10,25,50]; WINDOWS={'2019':'2019-01-01','2020':'2020-01-01','2022':'2022-01-01'}
def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)) if n>1 else 0.; return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1) if n else None,'maxdd':float((e/e.cummax()-1).min()) if n else None,'sharpe_rf0':float(q.mean()*12/vol) if vol else None}
def reb(r,cols,bps):
 target=pd.Series({c:1/len(cols) for c in cols},dtype=float); prev=None; out=[]; turns=[]; cost=bps/10000
 for _,row in r[cols].iterrows():
  turn=1.0 if prev is None else float((target-prev).abs().sum()/2); out.append(float((target*row).sum())-turn*cost); turns.append(turn)
  grown=target*(1+row); prev=grown/float(grown.sum())
 return pd.Series(out,index=r.index),pd.Series(turns,index=r.index)
def folds(a,b):
 z=pd.DataFrame({'a':a,'b':b}).dropna(); vals=[]
 for pos in np.array_split(np.arange(len(z)),5):
  c=z.iloc[pos]
  if len(c)>=12: vals.append(metric(c.a)['cagr']-metric(c.b)['cagr'])
 return vals
syms=CAND+BASE+[CONTROL]; raw=yf.download(syms,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[syms].dropna().resample('ME').last(); r=px.pct_change().dropna(); results={}
for bps in COSTS:
 cand,ct=reb(r,CAND,bps); base,bt=reb(r,BASE,bps); cr={}
 for w,start in WINDOWS.items():
  ix=r.index>=pd.Timestamp(start); a=cand.loc[ix]; b=base.loc[ix]; q=r.loc[ix,CONTROL]; f=folds(a,b); am=metric(a); bm=metric(b); qm=metric(q)
  cr[w]={'candidate':am,'matched':bm,'matched_excess_cagr':am['cagr']-bm['cagr'],'positive_matched_folds':sum(x>0 for x in f),'fold_count':len(f),'vs_QQQ_cagr':am['cagr']-qm['cagr'],'candidate_avg_monthly_turnover':float(ct.loc[ix].mean())}
 results[str(bps)]=cr
base=results['10']['2019']; stress25=results['25']['2019']; stress50=results['50']['2019']; ok=all(results[str(c)][w]['matched_excess_cagr']>0 for c in COSTS for w in WINDOWS) and all(results[str(c)]['2019']['positive_matched_folds']>=3 for c in COSTS)
out={'schema':'research.p291_spmo_calf_cost_r1','parent':'P291','claim':'Test whether the independently confirmed frozen 50/50 SPMO+CALF combination retains after-cost matched excess when one-way drift-rebalance costs rise from 10 to 25 and 50 bps, with no changes to components, weights, cadence, windows, or controls.','parameters':{'candidate':CAND,'matched':BASE,'weights':[0.5,0.5],'monthly_rebalance':True,'one_way_cost_bps':COSTS,'windows':WINDOWS,'no_tuning':True},'results':results,'decision_rule':'Cost robustness requires positive matched excess in 2019+, 2020+, and 2022+ at every 10/25/50 bp cost level and >=3/5 positive 2019+ chronology folds at every cost level. QQQ remains opportunity context only.','decision':'P291_SPMO_CALF_COST_ROBUST' if ok else 'P291_SPMO_CALF_COST_SENSITIVITY','limitations':['same adjusted-price provider and return sample as prior confirmation','turnover cost is a conservative explicit model, not observed fund execution slippage','scientific evidence only; no allocation/ranking/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p291_spmo_calf_cost_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
