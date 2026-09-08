from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import fixed_multifactor_cross_sectional_r1 as base
import p50_sector_walkforward_ridge_r1 as p50

SYMS=p50.SYMS; FEATURES=p50.FEATURES; TOP=3; MIN_MONTHS=60

def run():
 close=base.load(SYMS); panel,m=p50.build(close); dates=sorted(panel.date.unique()); prev={s:0. for s in SYMS}; rec=[]
 for i,dt in enumerate(dates):
  if i<MIN_MONTHS: continue
  tr=panel[panel.date<dt]; te=panel[panel.date==dt].copy()
  if len(tr)<MIN_MONTHS*len(SYMS) or len(te)!=len(SYMS): continue
  model=RandomForestRegressor(n_estimators=300,max_depth=3,min_samples_leaf=20,max_features='sqrt',random_state=53,n_jobs=-1)
  model.fit(tr[list(FEATURES)].to_numpy(),tr.target_excess.to_numpy()); te['pred']=model.predict(te[list(FEATURES)].to_numpy())
  chosen=te.sort_values('pred',ascending=False).head(TOP).symbol.tolist(); w={s:(1/TOP if s in chosen else 0.) for s in SYMS}; to=.5*sum(abs(w[s]-prev[s]) for s in SYMS); r=te.set_index('symbol').realized; nxt=pd.Timestamp(te.next_date.iloc[0]); start=pd.Timestamp(dt)
  rec.append({'date':nxt,'gross':sum(w[s]*float(r[s]) for s in SYMS),'ew':float(r.mean()),'spy':float(m.at[nxt,'SPY']/m.at[start,'SPY']-1),'qqq':float(m.at[nxt,'QQQ']/m.at[start,'QQQ']-1),'turnover':to}); prev=w
 return pd.DataFrame(rec).set_index('date'),close

def metric(fr,bps):
 c=fr.gross-fr.turnover*bps/10000; cm=base.metrics(c); em=base.metrics(fr.ew); sm=base.metrics(fr.spy); qm=base.metrics(fr.qqq); pos,folds=base.fold_count(c,fr.ew)
 return {'months':len(fr),'start':str(fr.index.min().date()),'end':str(fr.index.max().date()),'candidate':cm,'matched_ew':em,'spy':sm,'qqq':qm,'excess_cagr_vs_ew':cm['cagr']-em['cagr'],'excess_cagr_vs_spy':cm['cagr']-sm['cagr'],'excess_cagr_vs_qqq':cm['cagr']-qm['cagr'],'positive_folds_vs_ew':pos,'folds':folds,'mean_annual_turnover':float(fr.turnover.mean()*12)}
def main():
 fr,close=run(); tests={'full':{'25':metric(fr,25),'50':metric(fr,50)}}
 for start in ('2015-01-01','2020-01-01'):
  f=fr.loc[pd.Timestamp(start):]; tests[f'{start[:4]}_forward']={'25':metric(f,25),'50':metric(f,50)}
 out={'schema':'research.p53_sector_random_forest_r1','parent':'P53','hypothesis':'A prospectively frozen shallow nonlinear tree ensemble can extract causal cross-sectional sector selection signal that the fixed linear Ridge could not make cost robust.','scientific_contract':{'universe':list(SYMS),'features':list(FEATURES),'target':'next-month sector return minus cross-sectional mean','model':'RandomForestRegressor','params':{'n_estimators':300,'max_depth':3,'min_samples_leaf':20,'max_features':'sqrt','random_state':53},'min_training_months':MIN_MONTHS,'training':'expanding, strictly causal','top_k':TOP,'cadence':'monthly','costs_bps':[25,50],'comparators':['same-sector equal weight','SPY','QQQ'],'no_hyperparameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'tests':tests}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p53_sector_random_forest_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:{'excess25_vs_ew':v['25']['excess_cagr_vs_ew'],'folds25':v['25']['positive_folds_vs_ew'],'excess50_vs_ew':v['50']['excess_cagr_vs_ew'],'vs_spy25':v['25']['excess_cagr_vs_spy'],'vs_qqq25':v['25']['excess_cagr_vs_qqq']} for k,v in tests.items()},sort_keys=True))
if __name__=='__main__': main()
