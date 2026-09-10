from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf
CANDIDATE='KMLM'; MATCHED='BIL'; BROAD='SPY'; COST_BPS=25; START='2021-01-01'
def stats(s):
 s=s.dropna(); r=s.pct_change().dropna(); years=(s.index[-1]-s.index[0]).days/365.25; wealth=(s.iloc[-1]/s.iloc[0])*(1-COST_BPS/10000.0)**2
 cagr=wealth**(1/years)-1; curve=s/s.iloc[0]; dd=(curve/curve.cummax()-1).min(); sh=(r.mean()/r.std()*math.sqrt(252)) if r.std()>0 else float('nan')
 return {'start':str(s.index[0].date()),'end':str(s.index[-1].date()),'n':int(len(s)),'cagr':float(cagr),'max_drawdown':float(dd),'sharpe':float(sh)}
x=yf.download([CANDIDATE,MATCHED,BROAD],start=START,auto_adjust=True,progress=False,threads=False); c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x; px=c.dropna()
windows=['2021-01-01','2022-01-01','2023-01-01']; res={}
for st in windows:
 z=px.loc[st:]; cs,ms,bs=stats(z[CANDIDATE]),stats(z[MATCHED]),stats(z[BROAD]); res[st]={'candidate':cs,'matched':ms,'broad':bs,'matched_excess_cagr':cs['cagr']-ms['cagr'],'broad_excess_cagr':cs['cagr']-bs['cagr']}
folds=[]
for y in [2021,2022,2023,2024,2025]:
 z=px.loc[f'{y}-01-01':f'{y}-12-31']
 if len(z)<120: continue
 cs,ms=stats(z[CANDIDATE]),stats(z[MATCHED]); folds.append({'year':y,'excess_cagr':cs['cagr']-ms['cagr'],'positive':cs['cagr']>ms['cagr'],'candidate_max_drawdown':cs['max_drawdown']})
pos=sum(x['positive'] for x in folds); pass_gate=all(res[x]['matched_excess_cagr']>0 for x in windows) and len(folds)>=5 and pos>=4
out={'schema':'research.p382_managed_futures_replication.v1','workload_id':'P382_MANAGED_FUTURES_REPLICATION_R1','parent_context':'P380','claim':'Replicate P380 managed-futures cash-plus premium with independent implementation KMLM against the same BIL control and 25 bp endpoint costs.','candidate':'KMLM','matched_control':'BIL','broad_control':'SPY','cost_bps_each_endpoint':COST_BPS,'fixed_windows':res,'calendar_folds':folds,'positive_matched_folds':pos,'decision_rule':'PASS only if matched excess positive from 2021+/2022+/2023+ and >=4/5 fixed 2021-2025 folds. No ticker/window/cost tuning.','decision':'MANAGED_FUTURES_IMPLEMENTATION_REPLICATION_SUPPORTED' if pass_gate else 'MANAGED_FUTURES_IMPLEMENTATION_REPLICATION_NOT_SUPPORTED','scientific_consequence':('Independent implementation replication supports a bounded managed-futures cash-plus family claim; next falsifier should be source/representation or complementarity, not parameter tuning.' if pass_gate else 'Preserve P380 DBMF-specific evidence but do not promote the broad managed-futures family; no parameter rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p382_managed_futures_replication_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_matched_folds':pos,'matched_excess':{k:res[k]['matched_excess_cagr'] for k in windows}},sort_keys=True))
