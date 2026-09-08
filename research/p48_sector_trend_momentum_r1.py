from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_deep_robustness_r2 as helper

SYMBOLS=tuple(base.UNIVERSES['sector']); FACTORS=('mom6','trend200'); TOP=3

def run():
 close=base.load(SYMBOLS); m,fm=helper.feature_maps(close); prev={s:0. for s in SYMBOLS}; rec=[]
 for dt in m.index:
  b=pd.DataFrame({f:fm[f].loc[dt,list(SYMBOLS)] for f in FACTORS},index=list(SYMBOLS))
  if b.isna().any().any(): continue
  score=b.rank(axis=0,pct=True,method='average').mean(axis=1); loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(SYMBOLS)]/m.loc[dt,list(SYMBOLS)]-1
  if r.isna().any(): continue
  chosen=score.sort_values(ascending=False).head(TOP).index.tolist(); w={s:(1/TOP if s in chosen else 0.) for s in SYMBOLS}; to=.5*sum(abs(w[s]-prev[s]) for s in SYMBOLS)
  rec.append({'date':nxt,'gross':sum(w[s]*float(r[s]) for s in SYMBOLS),'ew':float(r.mean()),'spy':float(close.resample('ME').last().at[nxt,'SPY']/close.resample('ME').last().at[dt,'SPY']-1),'qqq':float(close.resample('ME').last().at[nxt,'QQQ']/close.resample('ME').last().at[dt,'QQQ']-1),'turnover':to}); prev=w
 return pd.DataFrame(rec).set_index('date'),close

def score(fr,bps):
 c=fr.gross-fr.turnover*bps/10000; cm=base.metrics(c); bm=base.metrics(fr.ew); sm=base.metrics(fr.spy); qm=base.metrics(fr.qqq); pos,folds=base.fold_count(c,fr.ew)
 return {'months':len(fr),'start':str(fr.index.min().date()),'end':str(fr.index.max().date()),'candidate':cm,'matched_ew':bm,'spy':sm,'qqq':qm,'excess_cagr_vs_ew':cm['cagr']-bm['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr'],'positive_folds':pos,'folds':folds,'mean_annual_turnover':float(fr.turnover.mean()*12)}
def main():
 fr,close=run(); tests={'full':{'25':score(fr,25),'50':score(fr,50)}}
 for start in ('2015-01-01','2020-01-01'):
  f=fr.loc[pd.Timestamp(start):]; tests[f'{start[:4]}_forward']={'25':score(f,25),'50':score(f,50)}
 out={'schema':'research.p48_sector_trend_momentum_r1','parent':'P48','hypothesis':'A prospectively frozen parsimonious trend+momentum cross-sectional ranker transports to broad sectors with durable after-cost excess.','scientific_contract':{'universe':list(SYMBOLS),'factors':list(FACTORS),'top_k':TOP,'cadence':'monthly','costs_bps':[25,50],'comparators':['same-sector-universe equal weight','SPY','QQQ'],'temporal_holdouts':['2015-forward','2020-forward'],'no_posthoc_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p48_sector_trend_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:{'excess25':v['25']['excess_cagr_vs_ew'],'folds25':v['25']['positive_folds'],'excess50':v['50']['excess_cagr_vs_ew'],'vs_spy25':v['25']['excess_cagr_vs_spy'],'vs_qqq25':v['25']['excess_cagr_vs_qqq']} for k,v in tests.items()},sort_keys=True))
if __name__=='__main__': main()
