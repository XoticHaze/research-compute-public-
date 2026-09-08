from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SYMS=tuple(base.UNIVERSES['sector']); TOP=3

def run():
 close=base.load(SYMS); m=close.resample('ME').last(); mom1=m[list(SYMS)].pct_change(1); spyvol=(close['SPY'].pct_change().rolling(63,min_periods=50).std(ddof=0)*math.sqrt(252)).resample('ME').last(); volmed=spyvol.rolling(36,min_periods=24).median(); prev={s:0. for s in SYMS}; rec=[]
 for dt in m.index[:-1]:
  sig=mom1.loc[dt]
  if sig.isna().any() or pd.isna(spyvol.loc[dt]) or pd.isna(volmed.loc[dt]): continue
  loc=m.index.get_loc(dt); nxt=m.index[loc+1]; r=m.loc[nxt,list(SYMS)]/m.loc[dt,list(SYMS)]-1
  if r.isna().any(): continue
  chosen=sig.sort_values().head(TOP).index.tolist(); w={s:(1/TOP if s in chosen else 0.) for s in SYMS}; to=.5*sum(abs(w[s]-prev[s]) for s in SYMS)
  rec.append({'date':nxt,'gross':sum(w[s]*float(r[s]) for s in SYMS),'ew':float(r.mean()),'spy':float(m.at[nxt,'SPY']/m.at[dt,'SPY']-1),'qqq':float(m.at[nxt,'QQQ']/m.at[dt,'QQQ']-1),'turnover':to,'prior_high_vol':bool(spyvol.loc[dt]>volmed.loc[dt])}); prev=w
 return pd.DataFrame(rec).set_index('date'),close

def metric(fr,bps):
 c=fr.gross-fr.turnover*bps/10000; cm=base.metrics(c); em=base.metrics(fr.ew); sm=base.metrics(fr.spy); qm=base.metrics(fr.qqq); pos,folds=base.fold_count(c,fr.ew)
 return {'months':len(fr),'start':str(fr.index.min().date()),'end':str(fr.index.max().date()),'candidate':cm,'matched_ew':em,'spy':sm,'qqq':qm,'excess_cagr_vs_ew':cm['cagr']-em['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr'],'positive_folds_vs_ew':pos,'folds':folds,'mean_annual_turnover':float(fr.turnover.mean()*12)}
def main():
 fr,close=run(); tests={'full':{'25':metric(fr,25),'50':metric(fr,50)}}
 for start in ('2015-01-01','2020-01-01'):
  f=fr.loc[pd.Timestamp(start):]; tests[f'{start[:4]}_forward']={'25':metric(f,25),'50':metric(f,50)}
 for state,val in [('prior_high_vol',True),('prior_low_vol',False)]:
  f=fr[fr.prior_high_vol==val]; tests[state]={'25':metric(f,25),'50':metric(f,50)}
 out={'schema':'research.p55_sector_reversal_r1','parent':'P55','hypothesis':'A prospectively frozen one-month cross-sectional sector reversal portfolio captures a fund-level short-term reversal premium, with predeclared prior-volatility attribution testing whether any edge is state concentrated.','scientific_contract':{'universe':list(SYMS),'signal':'prior one-month return ascending','top_k':TOP,'cadence':'monthly','costs_bps':[25,50],'comparators':['same-sector equal weight','SPY','QQQ'],'state_attribution':'prior 63d SPY realized vol above versus below rolling 36-month median','temporal_holdouts':['2015-forward','2020-forward'],'no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p55_sector_reversal_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:{'excess25':v['25']['excess_cagr_vs_ew'],'folds25':v['25']['positive_folds_vs_ew'],'excess50':v['50']['excess_cagr_vs_ew'],'vs_spy25':v['25']['excess_cagr_vs_spy']} for k,v in tests.items()},sort_keys=True))
if __name__=='__main__': main()
