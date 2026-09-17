from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf
CANDIDATE='DBMF'; MATCHED='BIL'; BROAD='SPY'; COST_BPS=25; START='2020-01-01'
def stats(s):
 s=s.dropna(); r=s.pct_change().dropna(); years=(s.index[-1]-s.index[0]).days/365.25; wealth=(s.iloc[-1]/s.iloc[0])*(1-COST_BPS/10000.0)**2
 cagr=wealth**(1/years)-1; curve=s/s.iloc[0]; dd=(curve/curve.cummax()-1).min(); sh=(r.mean()/r.std()*math.sqrt(252)) if r.std()>0 else float('nan')
 return {'start':str(s.index[0].date()),'end':str(s.index[-1].date()),'n':int(len(s)),'cagr':float(cagr),'max_drawdown':float(dd),'sharpe':float(sh)}
x=yf.download([CANDIDATE,MATCHED,BROAD],start=START,auto_adjust=True,progress=False,threads=False); c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x; px=c.dropna()
windows=['2020-01-01','2022-01-01','2023-01-01']; res={}
for st in windows:
 z=px.loc[st:]; cs,ms,bs=stats(z[CANDIDATE]),stats(z[MATCHED]),stats(z[BROAD]); res[st]={'candidate':cs,'matched':ms,'broad':bs,'matched_excess_cagr':cs['cagr']-ms['cagr'],'broad_excess_cagr':cs['cagr']-bs['cagr']}
folds=[]
for y in [2020,2021,2022,2023,2024,2025]:
 z=px.loc[f'{y}-01-01':f'{y}-12-31']
 if len(z)<120: continue
 cs,ms=stats(z[CANDIDATE]),stats(z[MATCHED]); folds.append({'year':y,'candidate_cagr':cs['cagr'],'matched_cagr':ms['cagr'],'excess_cagr':cs['cagr']-ms['cagr'],'positive':cs['cagr']>ms['cagr'],'candidate_max_drawdown':cs['max_drawdown']})
pos=sum(x['positive'] for x in folds); pass_gate=all(res[x]['matched_excess_cagr']>0 for x in windows) and len(folds)>=6 and pos>=4
out={'schema':'research.p380_managed_futures_premium.v1','workload_id':'P380_MANAGED_FUTURES_PREMIUM_R1','claim':'Test whether fixed managed-futures ETF DBMF delivers durable after-cost absolute-return excess over Treasury-bill fund BIL, with SPY only as opportunity-cost context.','candidate':'DBMF','matched_control':'BIL','broad_control':'SPY','cost_bps_each_endpoint':COST_BPS,'fixed_windows':res,'calendar_folds':folds,'positive_matched_folds':pos,'decision_rule':'PASS only if after-cost matched excess CAGR is positive from 2020+, 2022+, and 2023+, and at least 4/6 fixed 2020-2025 calendar folds are positive. Drawdown and SPY opportunity cost reported; no ticker/window/cost tuning.','decision':'MANAGED_FUTURES_PREMIUM_SUPPORTED' if pass_gate else 'MANAGED_FUTURES_PREMIUM_NOT_SUPPORTED','scientific_consequence':('Preserve DBMF as implementation-level managed-futures absolute-return evidence; require independent managed-futures implementation before broad family support.' if pass_gate else 'Reject the fixed DBMF cash-plus formulation as durable all-window alpha; preserve any regime-specific diversification evidence and rotate without parameter rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p380_managed_futures_premium_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_matched_folds':pos,'matched_excess':{k:res[k]['matched_excess_cagr'] for k in windows}},sort_keys=True))
