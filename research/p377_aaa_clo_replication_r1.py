from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf
CANDIDATE='AAA'; MATCHED='SGOV'; BROAD='SPY'; COST_BPS=25; START='2021-01-01'
def stats(s):
 s=s.dropna(); r=s.pct_change().dropna(); years=(s.index[-1]-s.index[0]).days/365.25; wealth=(s.iloc[-1]/s.iloc[0])*(1-COST_BPS/10000.0)**2
 cagr=wealth**(1/years)-1; curve=s/s.iloc[0]; dd=(curve/curve.cummax()-1).min(); sh=(r.mean()/r.std()*math.sqrt(252)) if r.std()>0 else float('nan')
 return {'start':str(s.index[0].date()),'end':str(s.index[-1].date()),'n':int(len(s)),'cagr':float(cagr),'max_drawdown':float(dd),'sharpe':float(sh)}
try:
 x=yf.download([CANDIDATE,MATCHED,BROAD],start=START,auto_adjust=True,progress=False,threads=False)
 c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
 px=c.dropna() if isinstance(c,pd.DataFrame) else pd.DataFrame()
 source_ok=all(t in px.columns for t in [CANDIDATE,MATCHED,BROAD]) and len(px)>=1000
except Exception:
 px=pd.DataFrame(); source_ok=False
res={}; folds=[]
if source_ok:
 for st in ['2021-01-01','2022-01-01','2023-01-01']:
  z=px.loc[st:]; cs,ms,bs=stats(z[CANDIDATE]),stats(z[MATCHED]),stats(z[BROAD]); res[st]={'candidate':cs,'matched':ms,'broad':bs,'matched_excess_cagr':cs['cagr']-ms['cagr'],'broad_excess_cagr':cs['cagr']-bs['cagr']}
 for y in [2021,2022,2023,2024,2025]:
  z=px.loc[f'{y}-01-01':f'{y}-12-31']
  if len(z)>=120:
   cs,ms=stats(z[CANDIDATE]),stats(z[MATCHED]); folds.append({'year':y,'excess_cagr':cs['cagr']-ms['cagr'],'positive':cs['cagr']>ms['cagr']})
pos=sum(x['positive'] for x in folds)
pass_gate=source_ok and all(res[x]['matched_excess_cagr']>0 for x in ['2021-01-01','2022-01-01','2023-01-01']) and len(folds)>=5 and pos>=4
decision='AAA_CLO_IMPLEMENTATION_REPLICATION_SUPPORTED' if pass_gate else ('AAA_CLO_IMPLEMENTATION_REPLICATION_NOT_SUPPORTED' if source_ok else 'AAA_CLO_REPLICATION_SOURCE_NOT_USABLE')
out={'schema':'research.p377_aaa_clo_replication.v1','workload_id':'P377_AAA_CLO_REPLICATION_R1','parent_context':'P376','claim':'Replicate P376 cash-plus premium with independent CLO implementation AAF First Priority CLO Bond ETF (AAA) against the same SGOV matched control, same 25 bp endpoint costs, same fixed windows/folds.','candidate':'AAA','matched_control':'SGOV','broad_control':'SPY','cost_bps_each_endpoint':COST_BPS,'source_ok':source_ok,'fixed_windows':res,'calendar_folds':folds,'positive_matched_folds':pos,'decision_rule':'PASS only if source usable, matched excess positive from 2021+/2022+/2023+, and >=4/5 2021-2025 calendar folds positive. No ticker/window/cost tuning.','decision':decision,'scientific_consequence':('Independent implementation replication supports a broader AAA CLO cash-plus family claim; next test should be source/representation or regime robustness, not parameter tuning.' if pass_gate else ('Independent implementation materially fails the same claim; preserve P376 JAAA-specific evidence but do not promote the broad family.' if source_ok else 'DATA/SOURCE failure only; no model inference. Rotate to another independent representation or family.')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p377_aaa_clo_replication_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'source_ok':source_ok,'positive_matched_folds':pos,'matched_excess':{k:v.get('matched_excess_cagr') for k,v in res.items()}},sort_keys=True))
