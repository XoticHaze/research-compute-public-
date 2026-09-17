from __future__ import annotations
import json
from pathlib import Path
import pandas as pd, numpy as np, yfinance as yf
T=['XSMO','AVUV','IJR']; ENDPOINT=0.0025; REBAL_COST=0.0010
x=yf.download(T,start='2019-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().dropna().pct_change().dropna().loc['2020-01-01':]
def endpoint(s):
 y=s.copy()
 if len(y): y.iloc[0]-=ENDPOINT; y.iloc[-1]-=ENDPOINT
 return y
def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def monthly_rebalanced_costed(df):
 vals=[]; turns=[]
 for _,row in df.iterrows():
  gross=0.5*row.XSMO+0.5*row.AVUV
  denom=0.5*(1+row.XSMO)+0.5*(1+row.AVUV)
  w1=0.5*(1+row.XSMO)/denom
  turn=abs(0.5-w1)
  vals.append(gross-REBAL_COST*turn); turns.append(turn)
 return pd.Series(vals,index=df.index),pd.Series(turns,index=df.index)
def drifted_buyhold(df):
 w=np.array([0.5,0.5],float); out=[]
 for _,row in df.iterrows():
  rr=np.array([row.XSMO,row.AVUV],float); ret=float((w*rr).sum()); out.append(ret); w=w*(1+rr); w=w/w.sum()
 return pd.Series(out,index=df.index)
reb,turn=monthly_rebalanced_costed(r); drift=drifted_buyhold(r)
def ev(s,a,b=None):
 q=endpoint(s.loc[a:b]); ctl=endpoint(r.IJR.loc[a:b]); return {'months':len(q),'combo_cagr':cagr(q),'ijr_cagr':cagr(ctl),'matched_excess_pp':100*(cagr(q)-cagr(ctl))}
blocks=[('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]
reb_blocks=[ev(reb,a,b) for a,b in blocks]; drift_blocks=[ev(drift,a,b) for a,b in blocks]
reb_full=ev(reb,'2020-01-01'); drift_full=ev(drift,'2020-01-01')
passed=all(z['matched_excess_pp']>0 for z in reb_blocks+drift_blocks) and reb_full['matched_excess_pp']>0 and drift_full['matched_excess_pp']>0
out={'schema':'research.p421_smallcap_combo_implementation.v1','workload_id':'P421_SMALLCAP_COMBO_IMPLEMENTATION_R1','parent':'SMALL_CAP_FACTOR_COMPLEMENTARITY','claim':'The fixed 50/50 XSMO+AVUV combination remains positively matched versus IJR under two implementation-faithful variants: monthly rebalancing with explicit 10 bp per dollar one-way turnover plus 25 bp endpoint friction, and a 50/50 initial buy-and-hold drift implementation with endpoint friction.','endpoint_cost_bps_each':25,'monthly_rebalance_cost_bps_per_oneway_turnover':10,'mean_monthly_oneway_turnover':float(turn.mean()),'annualized_oneway_turnover':float(turn.mean()*12),'rebalanced_blocks':reb_blocks,'drifted_blocks':drift_blocks,'rebalanced_full':reb_full,'drifted_full':drift_full,'decision_rule':'IMPLEMENTATION_SUPPORTED only if both implementations retain positive after-cost combo-IJR excess in every fixed 2020-21/2022-23/2024+ block and full common history. No change to weight, products, windows, or costs after seeing results.','decision':'SMALL_CAP_FACTOR_COMBINATION_IMPLEMENTATION_SUPPORTED' if passed else 'SMALL_CAP_FACTOR_COMBINATION_IMPLEMENTATION_SENSITIVE','scientific_consequence':('P417/P420 complementarity survives explicit implementation-cost and rebalance-assumption adjudication; allocation authority remains outside Market Research.' if passed else 'Narrow P417/P420 to representation-level evidence because the fixed combination is implementation-sensitive. Preserve individual XSMO and AVUV evidence; do not weight-rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p421_smallcap_combo_implementation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'annualized_turnover':round(out['annualized_oneway_turnover'],3),'reb_blocks':[round(z['matched_excess_pp'],3) for z in reb_blocks],'drift_blocks':[round(z['matched_excess_pp'],3) for z in drift_blocks],'reb_full':round(reb_full['matched_excess_pp'],3),'drift_full':round(drift_full['matched_excess_pp'],3)},sort_keys=True))