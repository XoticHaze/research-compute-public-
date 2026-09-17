from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['EFV','EFA','ACWI']; COST=0.0025
x=yf.download(T,start='2005-01-01',auto_adjust=True,progress=False,threads=False)
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
 q=charge(r.EFV.loc[a:b]); v=charge(r.EFA.reindex(q.index)); s=charge(r.ACWI.reindex(q.index))
 return {'start':a,'end':b,'months':int(len(q)),'efv_cagr':cagr(q),'efa_cagr':cagr(v),'acwi_cagr':cagr(s),'matched_excess_pp':100*(cagr(q)-cagr(v)),'acwi_excess_pp':100*(cagr(q)-cagr(s)),'efv_sharpe':sh(q),'efa_sharpe':sh(v),'efv_max_drawdown':dd(q),'efa_max_drawdown':dd(v)}
windows={k:evalw(v) for k,v in {'2006+':'2006-01-01','2015+':'2015-01-01','2020+':'2020-01-01'}.items()}
folds=[]
for a,b in [('2006-01-01','2009-12-31'),('2010-01-01','2013-12-31'),('2014-01-01','2017-12-31'),('2018-01-01','2021-12-31'),('2022-01-01',None)]:
 z=evalw(a,b); z['positive_matched_excess']=bool(z['matched_excess_pp']>0); folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds)
pass_gate=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=4
out={'schema':'research.p392_international_value.v1','workload_id':'P392_INTERNATIONAL_VALUE_R1','parent':'DEVELOPED_EX_US_VALUE_PREMIUM','claim':'Prospectively fixed developed ex-US value exposure via EFV can deliver durable after-cost excess return over EFA, with ACWI opportunity-cost context, without timing, leverage, or parameter search.','fund':'EFV','matched_control':'EFA','opportunity_control':'ACWI','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'decision_rule':'SUPPORTED only if EFV has positive after-cost CAGR excess versus EFA in fixed 2006+/2015+/2020+ windows and >=4/5 chronological folds are positive. No product/date/cost/timing/weight tuning after observation.','decision':'INTERNATIONAL_VALUE_SUPPORTED' if pass_gate else 'INTERNATIONAL_VALUE_NOT_SUPPORTED','scientific_consequence':('Developed ex-US value earns initial standalone survivor status requiring orthogonal representation and complementarity validation; no portfolio allocation authority follows.' if pass_gate else 'Reject this exact EFV developed ex-US value formulation, preserve passing eras/risk dimensions only, and do not product/date/cost rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p392_international_value_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))