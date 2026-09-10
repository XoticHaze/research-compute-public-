from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['DWAS','IJR','VB']; COST=0.0025
x=yf.download(T,start='2012-07-01',auto_adjust=True,progress=False,threads=False)
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
 q=charge(r.DWAS.loc[a:b]); i=charge(r.IJR.reindex(q.index)); v=charge(r.VB.reindex(q.index))
 return {'start':a,'end':b,'months':int(len(q)),'dwas_cagr':cagr(q),'ijr_cagr':cagr(i),'vb_cagr':cagr(v),'matched_excess_pp':100*(cagr(q)-cagr(i)),'vb_excess_pp':100*(cagr(q)-cagr(v)),'dwas_sharpe':sh(q),'ijr_sharpe':sh(i),'dwas_max_drawdown':dd(q),'ijr_max_drawdown':dd(i)}
windows={k:evalw(v) for k,v in {'2013+':'2013-01-01','2020+':'2020-01-01','2022+':'2022-01-01'}.items()}
folds=[]
for a,b in [('2013-01-01','2015-12-31'),('2016-01-01','2018-12-31'),('2019-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]:
 z=evalw(a,b); z['positive_matched_excess']=bool(z['matched_excess_pp']>0); folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds)
pass_gate=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=4
out={'schema':'research.p397_smallcap_momentum_representation.v1','workload_id':'P397_SMALLCAP_MOMENTUM_REPRESENTATION_R1','parent':'US_SMALL_CAP_MOMENTUM_TRANSPORT','claim':'An independent Dorsey-Wright small-cap momentum representation via DWAS can reproduce durable after-cost excess over IJR, with VB opportunity-cost context, supporting P395 transport beyond one index/product implementation.','fund':'DWAS','matched_control':'IJR','opportunity_control':'VB','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'decision_rule':'REPRESENTATION_SUPPORTED only if DWAS has positive after-cost CAGR excess versus IJR in fixed 2013+/2020+/2022+ windows and >=4/5 chronological folds are positive. No product/date/cost/timing/weight tuning after observation.','decision':'SMALLCAP_MOMENTUM_REPRESENTATION_SUPPORTED' if pass_gate else 'SMALLCAP_MOMENTUM_REPRESENTATION_NOT_SUPPORTED','scientific_consequence':('P395 gains independent-representation support for a broader small-cap momentum mechanism while retaining observed regime weaknesses; no portfolio allocation authority follows.' if pass_gate else 'Independent representation does not confirm the broader small-cap momentum claim. Preserve P395 XSMO passing evidence and scope, record this representation failure, and do not demote P395 solely on this one orthogonal failure.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p397_smallcap_momentum_representation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))