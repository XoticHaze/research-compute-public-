from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['SYLD','VTI','SPY']; COST=0.0025
x=yf.download(T,start='2013-05-01',auto_adjust=True,progress=False,threads=False)
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
 q=charge(r.SYLD.loc[a:b]); v=charge(r.VTI.reindex(q.index)); s=charge(r.SPY.reindex(q.index))
 return {'start':a,'end':b,'months':int(len(q)),'syld_cagr':cagr(q),'vti_cagr':cagr(v),'spy_cagr':cagr(s),'matched_excess_pp':100*(cagr(q)-cagr(v)),'spy_excess_pp':100*(cagr(q)-cagr(s)),'syld_sharpe':sh(q),'vti_sharpe':sh(v),'syld_max_drawdown':dd(q),'vti_max_drawdown':dd(v)}
windows={k:evalw(v) for k,v in {'2014+':'2014-01-01','2020+':'2020-01-01','2022+':'2022-01-01'}.items()}
folds=[]
for a,b in [('2014-01-01','2015-12-31'),('2016-01-01','2017-12-31'),('2018-01-01','2020-12-31'),('2021-01-01','2023-12-31'),('2024-01-01',None)]:
 z=evalw(a,b); z['positive_matched_excess']=bool(z['matched_excess_pp']>0); folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds)
pass_gate=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=4
out={'schema':'research.p390_shareholder_yield_premium.v1','workload_id':'P390_SHAREHOLDER_YIELD_PREMIUM_R1','parent':'US_SHAREHOLDER_YIELD_FACTOR_PREMIUM','claim':'Prospectively fixed shareholder-yield equity exposure via SYLD can deliver durable after-cost excess return over broad US equity VTI, with SPY as opportunity-cost context, without timing, leverage, or parameter search.','fund':'SYLD','matched_control':'VTI','opportunity_control':'SPY','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'decision_rule':'SUPPORTED only if SYLD has positive after-cost CAGR excess versus VTI in fixed 2014+/2020+/2022+ windows and >=4/5 chronological folds are positive. No product/date/cost/timing/weight tuning after observation.','decision':'SHAREHOLDER_YIELD_PREMIUM_SUPPORTED' if pass_gate else 'SHAREHOLDER_YIELD_PREMIUM_NOT_SUPPORTED','scientific_consequence':('Shareholder-yield factor earns initial standalone survivor status requiring orthogonal representation validation and complementarity testing; no portfolio allocation authority follows.' if pass_gate else 'Reject this exact standalone SYLD shareholder-yield formulation, preserve passing eras/risk dimensions only, and do not product/date/cost rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p390_shareholder_yield_premium_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))