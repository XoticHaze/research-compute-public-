from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['AVDV','VSS','VXUS']; COST=0.0025
x=yf.download(T,start='2019-09-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
m=c[T].resample('ME').last().dropna(); r=m.pct_change().dropna()
if len(r)<60: raise SystemExit('SOURCE_FAILURE_SHORT_OVERLAP')
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
 q=charge(r.AVDV.loc[a:b]); s=charge(r.VSS.reindex(q.index)); h=charge(r.VXUS.reindex(q.index))
 return {'start':a,'end':b,'months':int(len(q)),'avdv_cagr':cagr(q),'vss_cagr':cagr(s),'vxus_cagr':cagr(h),'matched_excess_pp':100*(cagr(q)-cagr(s)),'vxus_excess_pp':100*(cagr(q)-cagr(h)),'avdv_sharpe':sh(q),'vss_sharpe':sh(s),'avdv_max_drawdown':dd(q),'vss_max_drawdown':dd(s)}
windows={k:evalw(v) for k,v in {'2020+':'2020-01-01','2022+':'2022-01-01','2024+':'2024-01-01'}.items()}
folds=[]
for a,b in [('2020-01-01','2020-12-31'),('2021-01-01','2021-12-31'),('2022-01-01','2022-12-31'),('2023-01-01','2023-12-31'),('2024-01-01','2024-12-31'),('2025-01-01',None)]:
 z=evalw(a,b); z['positive_matched_excess']=bool(z['matched_excess_pp']>0); folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds)
opp=sum(z['vxus_excess_pp']>0 for z in windows.values())
pass_gate=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=4 and opp>=2
out={'schema':'research.p401_international_small_value.v1','workload_id':'P401_INTERNATIONAL_SMALL_VALUE_R1','parent':'INTERNATIONAL_SMALL_VALUE_SELECTION_PREMIUM','claim':'Prospectively fixed international small-value exposure via AVDV can deliver durable after-cost excess return over VSS, with VXUS opportunity-cost context, without timing, leverage, or parameter search.','fund':'AVDV','matched_control':'VSS','opportunity_control':'VXUS','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'opportunity_windows_beaten':opp,'decision_rule':'SUPPORTED only if AVDV has positive after-cost CAGR excess versus VSS in fixed 2020+/2022+/2024+ windows, >=4/6 chronological folds are positive, and >=2/3 fixed windows beat VXUS. No product/date/cost/timing/weight tuning after observation.','decision':'INTERNATIONAL_SMALL_VALUE_SUPPORTED' if pass_gate else 'INTERNATIONAL_SMALL_VALUE_NOT_SUPPORTED','scientific_consequence':('International small-value earns initial standalone survivor status requiring orthogonal representation and complementarity validation; no portfolio allocation authority follows.' if pass_gate else 'Reject this exact AVDV-versus-VSS formulation as a durable standalone alpha claim, preserve passing eras/risk dimensions only, and do not product/date/cost rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p401_international_small_value_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'opportunity_windows_beaten':opp,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))
