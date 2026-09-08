from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
import fixed_multifactor_cross_sectional_r1 as base

SYMS=('EWA','EWC','EWG','EWJ','EWK','EWM','EWW','EWY'); TOP=3; ALPHA=1.0; MIN_MONTHS=60
FEATURES=('mom1','mom3','mom6','mom12','trend200','vol3','vol6','drawdown6')

def build(close):
 m=close.resample('ME').last(); dr=close.pct_change(); raw={
  'mom1':m.pct_change(1),'mom3':m.pct_change(3),'mom6':m.pct_change(6),'mom12':m.pct_change(12),
  'trend200':(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(),
  'vol3':(dr.rolling(63,min_periods=50).std(ddof=0)*math.sqrt(252)).resample('ME').last(),
  'vol6':(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(),
  'drawdown6':(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(),
 }; rows=[]
 for dt in m.index[:-1]:
  nxt=m.index[m.index.get_loc(dt)+1]; block=pd.DataFrame({f:raw[f].loc[dt,list(SYMS)] for f in FEATURES},index=list(SYMS))
  if block.isna().any().any(): continue
  ranks=block.rank(axis=0,pct=True,method='average'); ret=m.loc[nxt,list(SYMS)]/m.loc[dt,list(SYMS)]-1
  if ret.isna().any(): continue
  ex=ret-ret.mean()
  for s in SYMS: rows.append({'date':dt,'next_date':nxt,'symbol':s,**{f:float(ranks.at[s,f]) for f in FEATURES},'target_excess':float(ex[s]),'realized':float(ret[s])})
 return pd.DataFrame(rows),m

def run():
 close=base.load(SYMS); panel,m=build(close); dates=sorted(panel.date.unique()); prev={s:0. for s in SYMS}; prevmom={s:0. for s in SYMS}; rec=[]
 for i,dt in enumerate(dates):
  if i<MIN_MONTHS: continue
  tr=panel[panel.date<dt]; te=panel[panel.date==dt].copy()
  if len(tr)<MIN_MONTHS*len(SYMS) or len(te)!=len(SYMS): continue
  model=Ridge(alpha=ALPHA,fit_intercept=True); model.fit(tr[list(FEATURES)].to_numpy(),tr.target_excess.to_numpy()); te['pred']=model.predict(te[list(FEATURES)].to_numpy())
  chosen=te.sort_values('pred',ascending=False).head(TOP).symbol.tolist(); momchosen=te.sort_values('mom12',ascending=False).head(TOP).symbol.tolist(); w={s:(1/TOP if s in chosen else 0.) for s in SYMS}; wm={s:(1/TOP if s in momchosen else 0.) for s in SYMS}; to=.5*sum(abs(w[s]-prev[s]) for s in SYMS); tom=.5*sum(abs(wm[s]-prevmom[s]) for s in SYMS)
  r=te.set_index('symbol').realized; nxt=pd.Timestamp(te.next_date.iloc[0]); start=pd.Timestamp(dt)
  rec.append({'date':nxt,'gross':sum(w[s]*float(r[s]) for s in SYMS),'mom12_gross':sum(wm[s]*float(r[s]) for s in SYMS),'ew':float(r.mean()),'spy':float(m.at[nxt,'SPY']/m.at[start,'SPY']-1),'qqq':float(m.at[nxt,'QQQ']/m.at[start,'QQQ']-1),'turnover':to,'mom12_turnover':tom}); prev=w; prevmom=wm
 return pd.DataFrame(rec).set_index('date'),close

def metric(fr,bps):
 c=fr.gross-fr.turnover*bps/10000; mom=fr.mom12_gross-fr.mom12_turnover*bps/10000; cm=base.metrics(c); em=base.metrics(fr.ew); mm=base.metrics(mom); sm=base.metrics(fr.spy); qm=base.metrics(fr.qqq); pos,folds=base.fold_count(c,fr.ew)
 return {'months':len(fr),'start':str(fr.index.min().date()),'end':str(fr.index.max().date()),'candidate':cm,'matched_ew':em,'mom12_top3':mm,'spy':sm,'qqq':qm,'excess_cagr_vs_ew':cm['cagr']-em['cagr'],'excess_cagr_vs_mom12':cm['cagr']-mm['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr'],'positive_folds_vs_ew':pos,'folds':folds,'mean_annual_turnover':float(fr.turnover.mean()*12)}
def main():
 fr,close=run(); tests={'full':{'25':metric(fr,25),'50':metric(fr,50)}}
 for start in ('2015-01-01','2020-01-01'):
  f=fr.loc[pd.Timestamp(start):]; tests[f'{start[:4]}_forward']={'25':metric(f,25),'50':metric(f,50)}
 out={'schema':'research.p51_country_walkforward_ridge_r1','parent':'P51','scientific_contract':{'universe':list(SYMS),'features':list(FEATURES),'target':'next-month country return minus same-month cross-sectional mean','model':'Ridge','alpha':ALPHA,'min_training_months':MIN_MONTHS,'top_k':TOP,'cadence':'monthly','costs_bps':[25,50],'comparators':['same-country equal weight','12m-momentum top3','SPY','QQQ'],'no_hyperparameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p51_country_walkforward_ridge_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:{'excess25_vs_ew':v['25']['excess_cagr_vs_ew'],'excess25_vs_mom12':v['25']['excess_cagr_vs_mom12'],'folds25':v['25']['positive_folds_vs_ew'],'excess50_vs_ew':v['50']['excess_cagr_vs_ew'],'vs_spy25':v['25']['excess_cagr_vs_spy'],'vs_qqq25':v['25']['excess_cagr_vs_qqq']} for k,v in tests.items()},sort_keys=True))
if __name__=='__main__': main()
