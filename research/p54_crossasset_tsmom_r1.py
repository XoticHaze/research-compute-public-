from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

RISK=('SPY','TLT','GLD','DBC'); CASH='SHY'; ALL=RISK+(CASH,)

def run():
 close=base.load(ALL); m=close.resample('ME').last(); sig=m[list(RISK)].pct_change(12); prev={s:0. for s in ALL}; rec=[]
 for dt in m.index[:-1]:
  s=sig.loc[dt]
  if s.isna().any(): continue
  loc=m.index.get_loc(dt); nxt=m.index[loc+1]; r=m.loc[nxt,list(ALL)]/m.loc[dt,list(ALL)]-1
  if r.isna().any(): continue
  w={x:0. for x in ALL}
  for x in RISK:
   if float(s[x])>0: w[x]+=0.25
   else: w[CASH]+=0.25
  turn=.5*sum(abs(w[x]-prev[x]) for x in ALL)
  gross=sum(w[x]*float(r[x]) for x in ALL); ew=float(r[list(RISK)].mean())
  rec.append({'date':nxt,'gross':gross,'risk_ew':ew,'spy':float(r['SPY']),'qqq':float(m.at[nxt,'QQQ']/m.at[dt,'QQQ']-1),'turnover':turn,'risk_on_sleeves':sum(1 for x in RISK if w[x]>0)}); prev=w
 return pd.DataFrame(rec).set_index('date'),close

def metric(fr,bps):
 c=fr.gross-fr.turnover*bps/10000; cm=base.metrics(c); em=base.metrics(fr.risk_ew); sm=base.metrics(fr.spy); qm=base.metrics(fr.qqq); pos,folds=base.fold_count(c,fr.risk_ew)
 return {'months':len(fr),'start':str(fr.index.min().date()),'end':str(fr.index.max().date()),'candidate':cm,'matched_risk_ew':em,'spy':sm,'qqq':qm,'excess_cagr_vs_risk_ew':cm['cagr']-em['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr'],'positive_folds_vs_risk_ew':pos,'folds':folds,'mean_annual_turnover':float(fr.turnover.mean()*12),'mean_risk_on_sleeves':float(fr.risk_on_sleeves.mean())}
def main():
 fr,close=run(); tests={'full':{'25':metric(fr,25),'50':metric(fr,50),'100':metric(fr,100)}}
 for start in ('2010-01-01','2015-01-01','2020-01-01'):
  f=fr.loc[pd.Timestamp(start):]; tests[f'{start[:4]}_forward']={'25':metric(f,25),'50':metric(f,50),'100':metric(f,100)}
 out={'schema':'research.p54_crossasset_tsmom_r1','parent':'P54','hypothesis':'A prospectively frozen long-only 12-month time-series momentum overlay across equity, Treasury, gold, and commodity sleeves improves after-cost outcomes versus static equal-weight risk sleeves by moving negative-trend sleeve capital to short Treasuries.','scientific_contract':{'risk_universe':list(RISK),'defensive_asset':CASH,'signal':'own trailing 12-month price return > 0','allocation':'25% per risk sleeve when positive; otherwise that sleeve allocation to SHY','cadence':'monthly','costs_bps':[25,50,100],'comparators':['static equal weight of SPY/TLT/GLD/DBC','SPY','QQQ'],'temporal_holdouts':['2010-forward','2015-forward','2020-forward'],'no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p54_crossasset_tsmom_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:{'excess25':v['25']['excess_cagr_vs_risk_ew'],'folds25':v['25']['positive_folds_vs_risk_ew'],'excess50':v['50']['excess_cagr_vs_risk_ew'],'excess100':v['100']['excess_cagr_vs_risk_ew'],'vs_spy25':v['25']['excess_cagr_vs_spy'],'vs_qqq25':v['25']['excess_cagr_vs_qqq']} for k,v in tests.items()},sort_keys=True))
if __name__=='__main__': main()
