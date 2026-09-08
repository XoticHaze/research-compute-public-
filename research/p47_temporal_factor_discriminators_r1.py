from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SYMBOLS=base.UNIVERSES['industry']; FACTORS=('mom6','trend200','low_vol6','drawdown6')
def panel(close,factors):
 m=close.resample('ME').last(); dr=close.pct_change(); maps={'mom6':m.pct_change(6),'trend200':(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(),'low_vol6':-(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(),'drawdown6':(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last()}; rows=[]
 for dt in m.index:
  b=pd.DataFrame({f:maps[f].loc[dt,list(SYMBOLS)] for f in factors},index=list(SYMBOLS))
  if b.isna().any().any(): continue
  s=b.rank(axis=0,pct=True,method='average').mean(axis=1); rows += [{'month':dt,'symbol':x,'score':float(s[x])} for x in SYMBOLS]
 return pd.DataFrame(rows),m
def rets(close,factors):
 p,m=panel(close,factors); prev={s:0. for s in SYMBOLS}; out=[]
 for month in sorted(p.month.unique()):
  b=p[p.month==month].sort_values(['score','symbol'],ascending=[False,True]); loc=m.index.get_loc(month)
  if len(b)!=len(SYMBOLS) or not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(SYMBOLS)]/m.loc[month,list(SYMBOLS)]-1
  if r.isna().any(): continue
  chosen=b.head(3).symbol.tolist(); w={s:(1/3 if s in chosen else 0.) for s in SYMBOLS}; to=.5*sum(abs(w[s]-prev[s]) for s in SYMBOLS); out.append({'date':nxt,'gross':sum(w[s]*float(r[s]) for s in SYMBOLS),'ew':float(r.mean()),'turnover':to}); prev=w
 return pd.DataFrame(out).set_index('date')
def score(f,bps):
 c=f.gross-f.turnover*bps/10000; b=f.ew; cm=base.metrics(c); bm=base.metrics(b); pos,folds=base.fold_count(c,b); return {'months':len(f),'start':str(f.index.min().date()),'end':str(f.index.max().date()),'candidate':cm,'matched_ew':bm,'excess_cagr':cm['cagr']-bm['cagr'],'positive_folds':pos,'folds':folds}
def main():
 close=base.load(SYMBOLS); full=rets(close,FACTORS); tests={}
 for start in ('2015-01-01','2020-01-01'):
  f=full.loc[pd.Timestamp(start):]; tests[f'temporal_{start[:4]}_forward']={'25':score(f,25),'50':score(f,50)}
 for omitted in FACTORS:
  f=rets(close,tuple(x for x in FACTORS if x!=omitted)); tests[f'ablate_{omitted}']={'25':score(f,25),'50':score(f,50)}
 out={'schema':'research.p47_temporal_factor_discriminators_r1','parent':'P47','scientific_contract':{'universe':'industry','top_k':3,'costs_bps':[25,50],'comparator':'same-universe equal weight','no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p47_temporal_factor_discriminators_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:{'excess25':v['25']['excess_cagr'],'folds25':v['25']['positive_folds'],'excess50':v['50']['excess_cagr']} for k,v in tests.items()},sort_keys=True))
if __name__=='__main__': main()
