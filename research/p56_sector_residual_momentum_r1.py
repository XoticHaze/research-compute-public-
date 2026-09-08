from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SYMS=tuple(base.UNIVERSES['sector']); TOP=3; LOOKBACK=126

def run():
 close=base.load(SYMS); dr=close.pct_change(); m=close.resample('ME').last(); prev={s:0. for s in SYMS}; prevraw={s:0. for s in SYMS}; rec=[]
 beta={s:dr[s].rolling(LOOKBACK,min_periods=100).cov(dr['SPY'])/dr['SPY'].rolling(LOOKBACK,min_periods=100).var() for s in SYMS}
 resid=pd.DataFrame({s:dr[s]-beta[s]*dr['SPY'] for s in SYMS})
 resid_mom=(1+resid).rolling(LOOKBACK,min_periods=100).apply(np.prod,raw=True)-1
 sig=resid_mom.resample('ME').last(); raw=m[list(SYMS)].pct_change(6)
 for dt in m.index[:-1]:
  rs=sig.loc[dt,list(SYMS)]; rm=raw.loc[dt,list(SYMS)]
  if rs.isna().any() or rm.isna().any(): continue
  loc=m.index.get_loc(dt); nxt=m.index[loc+1]; r=m.loc[nxt,list(SYMS)]/m.loc[dt,list(SYMS)]-1
  if r.isna().any(): continue
  chosen=rs.sort_values(ascending=False).head(TOP).index.tolist(); rawchosen=rm.sort_values(ascending=False).head(TOP).index.tolist()
  w={s:(1/TOP if s in chosen else 0.) for s in SYMS}; wr={s:(1/TOP if s in rawchosen else 0.) for s in SYMS}; to=.5*sum(abs(w[s]-prev[s]) for s in SYMS); tor=.5*sum(abs(wr[s]-prevraw[s]) for s in SYMS)
  rec.append({'date':nxt,'gross':sum(w[s]*float(r[s]) for s in SYMS),'rawmom_gross':sum(wr[s]*float(r[s]) for s in SYMS),'ew':float(r.mean()),'spy':float(m.at[nxt,'SPY']/m.at[dt,'SPY']-1),'qqq':float(m.at[nxt,'QQQ']/m.at[dt,'QQQ']-1),'turnover':to,'rawmom_turnover':tor}); prev=w; prevraw=wr
 return pd.DataFrame(rec).set_index('date'),close

def metric(fr,bps):
 c=fr.gross-fr.turnover*bps/10000; raw=fr.rawmom_gross-fr.rawmom_turnover*bps/10000; cm=base.metrics(c); em=base.metrics(fr.ew); rm=base.metrics(raw); sm=base.metrics(fr.spy); qm=base.metrics(fr.qqq); pos,folds=base.fold_count(c,fr.ew)
 return {'months':len(fr),'start':str(fr.index.min().date()),'end':str(fr.index.max().date()),'candidate':cm,'matched_ew':em,'raw_mom6_top3':rm,'spy':sm,'qqq':qm,'excess_cagr_vs_ew':cm['cagr']-em['cagr'],'excess_cagr_vs_raw_mom6':cm['cagr']-rm['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr'],'positive_folds_vs_ew':pos,'folds':folds,'mean_annual_turnover':float(fr.turnover.mean()*12)}
def main():
 fr,close=run(); tests={'full':{'25':metric(fr,25),'50':metric(fr,50)}}
 for start in ('2015-01-01','2020-01-01'):
  f=fr.loc[pd.Timestamp(start):]; tests[f'{start[:4]}_forward']={'25':metric(f,25),'50':metric(f,50)}
 out={'schema':'research.p56_sector_residual_momentum_r1','parent':'P56','hypothesis':'A prospectively frozen market-beta-adjusted six-month residual-momentum ranker contains sector-selection information beyond raw six-month momentum and static sector exposure.','scientific_contract':{'universe':list(SYMS),'beta_window_days':LOOKBACK,'residual_signal':'126-day compounded sector residual return after rolling SPY beta adjustment','top_k':TOP,'cadence':'monthly','costs_bps':[25,50],'comparators':['same-sector equal weight','raw 6m momentum top3','SPY','QQQ'],'temporal_holdouts':['2015-forward','2020-forward'],'no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p56_sector_residual_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:{'excess25_vs_ew':v['25']['excess_cagr_vs_ew'],'excess25_vs_raw':v['25']['excess_cagr_vs_raw_mom6'],'folds25':v['25']['positive_folds_vs_ew'],'excess50_vs_ew':v['50']['excess_cagr_vs_ew'],'vs_spy25':v['25']['excess_cagr_vs_spy'],'vs_qqq25':v['25']['excess_cagr_vs_qqq']} for k,v in tests.items()},sort_keys=True))
if __name__=='__main__': main()
