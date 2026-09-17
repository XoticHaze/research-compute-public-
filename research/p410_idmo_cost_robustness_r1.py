from __future__ import annotations
import json
from pathlib import Path
import pandas as pd, yfinance as yf
T=['IDMO','EFA','ACWI']; COSTS=[0.001,0.0025,0.005]
x=yf.download(T,start='2017-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().dropna().pct_change().dropna()
def charge(s,cost):
 y=s.copy()
 if len(y): y.iloc[0]-=cost; y.iloc[-1]-=cost
 return y
def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def evalw(a,b,cost):
 q=charge(r.IDMO.loc[a:b],cost); ctl=charge(r.EFA.reindex(q.index),cost); opp=charge(r.ACWI.reindex(q.index),cost)
 return {'months':int(len(q)),'matched_excess_pp':100*(cagr(q)-cagr(ctl)),'acwi_excess_pp':100*(cagr(q)-cagr(opp))}
results={}
for cost in COSTS:
 k=f'{int(cost*10000)}bp_each_endpoint'
 windows={name:evalw(start,None,cost) for name,start in [('2018+','2018-01-01'),('2020+','2020-01-01'),('2022+','2022-01-01')]}
 folds=[]
 for a,b in [('2018-01-01','2019-12-31'),('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]:
  z=evalw(a,b,cost); z['positive_matched_excess']=z['matched_excess_pp']>0; folds.append(z)
 results[k]={'windows':windows,'positive_folds':sum(z['positive_matched_excess'] for z in folds),'folds':folds}
pass_gate=all(all(v['matched_excess_pp']>0 for v in z['windows'].values()) and z['positive_folds']>=3 for z in results.values())
out={'schema':'research.p410_idmo_cost_robustness.v1','workload_id':'P410_IDMO_COST_ROBUSTNESS_R1','parent':'INTERNATIONAL_MOMENTUM','claim':'The fixed P407 IDMO representation retains matched excess under prospectively fixed higher endpoint-friction stress without changing product, dates, control, or model.','results':results,'decision_rule':'COST_ROBUST only if each 10/25/50 bp endpoint-cost case remains positive versus EFA in every fixed 2018+/2020+/2022+ window and has >=3/4 positive chronology folds. No parameter/product rescue.','decision':'COST_ROBUST' if pass_gate else 'COST_ROBUSTNESS_NOT_ESTABLISHED','scientific_consequence':('P407 retains scoped survivor status under fixed 10/25/50 bp endpoint-friction stress. Close nearby retrospective cost testing and move to forward/implementation evidence.' if pass_gate else 'Record cost sensitivity as an independent weakness without erasing P407 passing evidence; do not tune products/windows/cost assumptions to rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p410_idmo_cost_robustness_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'cases':{k:{'positive_folds':v['positive_folds'],'windows':{w:round(x['matched_excess_pp'],3) for w,x in v['windows'].items()}} for k,v in results.items()}},sort_keys=True))
