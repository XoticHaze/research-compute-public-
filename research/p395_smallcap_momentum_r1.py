from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['XSMO','IJR','VB']; COST=0.0025
x=yf.download(T,start='2017-04-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
m=c[T].resample('ME').last().dropna(); r=m.pct_change().dropna()
def charge(s):
 y=s.copy()
 if len(y): y.iloc[0]-=COST; y.iloc[-1]-=COST
 return y
def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def sh(s):
 sd=s.std(ddof=1); return float(np.sqrt(12)*s.mean()/sd) if len(s)>1 and sd>0 else float('nan')
def dd(s):
 w=(1+s).cumprod(); return float((w/w.cummax()-1).min()) if len(s) else float('nan')
def evalw(a,b=None):
 q=charge(r.XSMO.loc[a:b]); i=charge(r.IJR.reindex(q.index)); v=charge(r.VB.reindex(q.index))
 return {'start':a,'end':b,'months':int(len(q)),'xsmo_cagr':cagr(q),'ijr_cagr':cagr(i),'vb_cagr':cagr(v),'matched_excess_pp':100*(cagr(q)-cagr(i)),'vb_excess_pp':100*(cagr(q)-cagr(v)),'xsmo_sharpe':sh(q),'ijr_sharpe':sh(i),'xsmo_max_drawdown':dd(q),'ijr_max_drawdown':dd(i)}
windows={k:evalw(v) for k,v in {'2018+':'2018-01-01','2020+':'2020-01-01','2022+':'2022-01-01'}.items()}
folds=[]
for a,b in [('2018-01-01','2018-12-31'),('2019-01-01','2020-12-31'),('2021-01-01','2022-12-31'),('2023-01-01','2024-12-31'),('2025-01-01',None)]:
 z=evalw(a,b); z['positive_matched_excess']=bool(z['matched_excess_pp']>0); folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds)
pass_gate=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=4
out={'schema':'research.p395_smallcap_momentum.v1','workload_id':'P395_SMALLCAP_MOMENTUM_R1','parent':'US_SMALL_CAP_MOMENTUM_TRANSPORT','claim':'Prospectively fixed small-cap momentum exposure via XSMO can deliver durable after-cost excess return over IJR, with VB opportunity-cost context, without timing, leverage, or parameter search.','fund':'XSMO','matched_control':'IJR','opportunity_control':'VB','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'decision_rule':'SUPPORTED only if XSMO has positive after-cost CAGR excess versus IJR in fixed 2018+/2020+/2022+ windows and >=4/5 chronological folds are positive. No product/date/cost/timing/weight tuning after observation.','decision':'SMALLCAP_MOMENTUM_SUPPORTED' if pass_gate else 'SMALLCAP_MOMENTUM_NOT_SUPPORTED','scientific_consequence':('Small-cap momentum transport earns initial survivor status requiring orthogonal representation/chronology validation; no portfolio allocation authority follows.' if pass_gate else 'Reject this exact XSMO small-cap momentum transport formulation, preserve passing eras/risk dimensions only, and do not product/date/cost rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p395_smallcap_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))