from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['MOAT','SPY','VTI']; COST=0.0025
x=yf.download(T,start='2012-04-01',auto_adjust=True,progress=False,threads=False)
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
 q=charge(r.MOAT.loc[a:b]); s=charge(r.SPY.reindex(q.index)); v=charge(r.VTI.reindex(q.index))
 return {'start':a,'end':b,'months':int(len(q)),'moat_cagr':cagr(q),'spy_cagr':cagr(s),'vti_cagr':cagr(v),'matched_excess_pp':100*(cagr(q)-cagr(s)),'vti_excess_pp':100*(cagr(q)-cagr(v)),'moat_sharpe':sh(q),'spy_sharpe':sh(s),'moat_max_drawdown':dd(q),'spy_max_drawdown':dd(s)}
windows={k:evalw(v) for k,v in {'2013+':'2013-01-01','2020+':'2020-01-01','2022+':'2022-01-01'}.items()}
folds=[]
for a,b in [('2013-01-01','2015-12-31'),('2016-01-01','2018-12-31'),('2019-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]:
 z=evalw(a,b); z['positive_matched_excess']=bool(z['matched_excess_pp']>0); folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds)
pass_gate=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=4
out={'schema':'research.p394_moat_selection.v1','workload_id':'P394_MOAT_SELECTION_R1','parent':'US_ECONOMIC_MOAT_SELECTION_PREMIUM','claim':'Prospectively fixed economic-moat selection via MOAT can deliver durable after-cost excess return over SPY, with VTI opportunity-cost context, without timing, leverage, or parameter search.','fund':'MOAT','matched_control':'SPY','opportunity_control':'VTI','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'decision_rule':'SUPPORTED only if MOAT has positive after-cost CAGR excess versus SPY in fixed 2013+/2020+/2022+ windows and >=4/5 chronological folds are positive. No product/date/cost/timing/weight tuning after observation.','decision':'MOAT_SELECTION_SUPPORTED' if pass_gate else 'MOAT_SELECTION_NOT_SUPPORTED','scientific_consequence':('Economic-moat selection earns initial standalone survivor status requiring orthogonal representation/chronology validation before any combination claim; no portfolio allocation authority follows.' if pass_gate else 'Reject this exact MOAT formulation, preserve passing eras/risk dimensions only, and do not product/date/cost rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p394_moat_selection_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))