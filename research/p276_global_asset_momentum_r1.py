from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ASSETS=['SPY','EFA','EEM','IEF','GLD','DBC']; LOOKBACK=252; SKIP=21; TOP=2
START='2007-01-01'; END='2026-09-10'; COSTS=[10.,25.,50.]; WINDOWS={'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01','2022':'2022-01-01'}

def metric(r):
 q=pd.Series(r,dtype=float).dropna(); e=(1+q).cumprod(); n=len(q); vol=float(q.std(ddof=1)*math.sqrt(12)); ann=float(q.mean()*12)
 return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}
def turn(a,b): return 0.5*sum(abs(b.get(s,0)-a.get(s,0)) for s in set(a)|set(b))
def folds(a,b):
 z=pd.DataFrame({'a':a,'b':b}).dropna(); out=[]
 for c in np.array_split(z,5):
  if len(c)>=6: out.append(metric(c.a)['cagr']-metric(c.b)['cagr'])
 return out
raw=yf.download(ASSETS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[ASSETS].dropna().sort_index()
mes=[i for i in range(LOOKBACK,len(px)-1) if px.index[i].month!=px.index[i+1].month]
rows=[]; prev={}
for n,i in enumerate(mes[:-1]):
 j=mes[n+1]; score={s:float(px[s].iloc[i-SKIP]/px[s].iloc[i-LOOKBACK]-1) for s in ASSETS}; sel=sorted(ASSETS,key=lambda s:(-score[s],s))[:TOP]
 w={s:1/TOP for s in sel}; t=turn(prev,w); prev=w; gross=sum(wt*float(px[s].iloc[j]/px[s].iloc[i]-1) for s,wt in w.items()); ew=float(np.mean([px[s].iloc[j]/px[s].iloc[i]-1 for s in ASSETS]))
 rows.append({'date':px.index[j],**{f'model_{int(c)}':gross-t*c/10000 for c in COSTS},'matched':ew,'SPY':float(px.SPY.iloc[j]/px.SPY.iloc[i]-1),'turnover':t})
r=pd.DataFrame(rows).set_index('date'); result={}
for name,start in WINDOWS.items():
 z=r.loc[r.index>=pd.Timestamp(start)]; m=metric(z.model_25); ew=metric(z.matched); spy=metric(z.SPY); f=folds(z.model_25,z.matched)
 result[name]={'model_25bps':m,'matched_equal_asset':ew,'SPY':spy,'matched_excess_cagr':m['cagr']-ew['cagr'],'vs_SPY_cagr':m['cagr']-spy['cagr'],'positive_matched_folds':sum(x>0 for x in f),'fold_count':len(f),'fold_excess_cagr':f,'matched_excess_50bps':metric(z.model_50)['cagr']-ew['cagr'],'mean_monthly_turnover':float(z.turnover.mean())}
p=result['2015']; q=result['2020']; s=result['2022']
passgate=p['matched_excess_cagr']>=.01 and p['positive_matched_folds']>=4 and p['matched_excess_50bps']>0 and q['matched_excess_cagr']>0 and q['positive_matched_folds']>=3 and s['matched_excess_cagr']>0
out={'schema':'research.p276_global_asset_momentum_r1','parent':'P276','hypothesis':'A prospectively fixed 12-1 top-2 cross-sectional momentum selector across US equity, developed ex-US, emerging markets, intermediate Treasuries, gold, and broad commodities creates durable after-cost excess versus equal-weight exposure to exactly the same assets.','parameters':{'assets':ASSETS,'lookback_sessions':LOOKBACK,'skip_sessions':SKIP,'top_n':TOP,'costs_bps':COSTS,'windows':WINDOWS},'results':result,'decision_rule':'SUPPORTED_CANDIDATE only if 2015+ matched excess >=1pp with >=4/5 positive folds and positive at 50bps, plus positive matched excess in 2020+ with >=3/5 folds and positive 2022+ matched excess. Otherwise reject this fixed formulation without parameter rescue.','decision':'P276_GLOBAL_ASSET_MOMENTUM_SUPPORTED_CANDIDATE' if passgate else 'P276_GLOBAL_ASSET_MOMENTUM_NOT_SUPPORTED','limitations':['Yahoo adjusted-price public research data','no lookback/top-k/universe tuning','cross-sectional momentum distinct from previously rejected absolute time-series timing overlays'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p276_global_asset_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
