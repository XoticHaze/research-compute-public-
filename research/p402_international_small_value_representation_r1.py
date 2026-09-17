from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['DLS','VSS','VXUS']; COST=0.0025
x=yf.download(T,start='2009-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
m=c[T].resample('ME').last().dropna(); r=m.pct_change().dropna()
if len(r)<150: raise SystemExit('SOURCE_FAILURE_SHORT_OVERLAP')
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
 q=charge(r.DLS.loc[a:b]); s=charge(r.VSS.reindex(q.index)); h=charge(r.VXUS.reindex(q.index))
 return {'start':a,'end':b,'months':int(len(q)),'dls_cagr':cagr(q),'vss_cagr':cagr(s),'vxus_cagr':cagr(h),'matched_excess_pp':100*(cagr(q)-cagr(s)),'vxus_excess_pp':100*(cagr(q)-cagr(h)),'dls_sharpe':sh(q),'vss_sharpe':sh(s),'dls_max_drawdown':dd(q),'vss_max_drawdown':dd(s)}
windows={k:evalw(v) for k,v in {'2010+':'2010-01-01','2015+':'2015-01-01','2020+':'2020-01-01'}.items()}
folds=[]
for a,b in [('2010-01-01','2012-12-31'),('2013-01-01','2015-12-31'),('2016-01-01','2018-12-31'),('2019-01-01','2021-12-31'),('2022-01-01',None)]:
 z=evalw(a,b); z['positive_matched_excess']=bool(z['matched_excess_pp']>0); folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds)
pass_gate=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=4
out={'schema':'research.p402_international_small_value_representation.v1','workload_id':'P402_INTERNATIONAL_SMALL_VALUE_REPRESENTATION_R1','parent':'INTERNATIONAL_SMALL_VALUE_SELECTION_PREMIUM','claim':'A long-history independent small-cap value/dividend representation via DLS can reproduce durable after-cost excess over VSS, with VXUS opportunity-cost context, supporting P401 beyond one AVDV implementation.','fund':'DLS','matched_control':'VSS','opportunity_control':'VXUS','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'decision_rule':'REPRESENTATION_SUPPORTED only if DLS has positive after-cost CAGR excess versus VSS in fixed 2010+/2015+/2020+ windows and >=4/5 chronological folds are positive. No product/date/cost/timing/weight tuning after observation.','decision':'INTERNATIONAL_SMALL_VALUE_REPRESENTATION_SUPPORTED' if pass_gate else 'INTERNATIONAL_SMALL_VALUE_REPRESENTATION_NOT_SUPPORTED','scientific_consequence':('Independent long-history representation supports a broader international small-value selection effect; P401 still requires complementarity/forward adjudication before any stronger claim.' if pass_gate else 'Independent long-history representation does not confirm the broader international small-value claim. Preserve P401 AVDV passing evidence and supported scope, record this representation failure, and do not demote P401 solely on this one orthogonal failure.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p402_international_small_value_representation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))
