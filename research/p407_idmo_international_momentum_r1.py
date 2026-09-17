from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['IDMO','EFA','ACWI']; COST=0.0025
x=yf.download(T,start='2017-01-01',auto_adjust=True,progress=False,threads=False)
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
 q=charge(r.IDMO.loc[a:b]); v=charge(r.EFA.reindex(q.index)); s=charge(r.ACWI.reindex(q.index))
 return {'start':a,'end':b,'months':int(len(q)),'idmo_cagr':cagr(q),'efa_cagr':cagr(v),'acwi_cagr':cagr(s),'matched_excess_pp':100*(cagr(q)-cagr(v)),'acwi_excess_pp':100*(cagr(q)-cagr(s)),'idmo_sharpe':sh(q),'efa_sharpe':sh(v),'idmo_max_drawdown':dd(q),'efa_max_drawdown':dd(v)}
windows={k:evalw(v) for k,v in {'2018+':'2018-01-01','2020+':'2020-01-01','2022+':'2022-01-01'}.items()}
folds=[]
for a,b in [('2018-01-01','2019-12-31'),('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]:
 z=evalw(a,b); z['positive_matched_excess']=bool(z['matched_excess_pp']>0); folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds); opp=sum(z['acwi_excess_pp']>0 for z in windows.values())
pass_gate=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=3 and opp>=2
out={'schema':'research.p407_idmo_international_momentum.v1','workload_id':'P407_IDMO_INTERNATIONAL_MOMENTUM_R1','parent':'INTERNATIONAL_MOMENTUM','claim':'After academic source-level mechanism support, a prospectively fixed independent investable international momentum representation via IDMO can deliver durable after-cost excess over EFA with ACWI opportunity-cost context.','fund':'IDMO','matched_control':'EFA','opportunity_control':'ACWI','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'opportunity_windows_beaten':opp,'decision_rule':'SUPPORTED only if matched excess is positive in fixed 2018+/2020+/2022+ windows, >=3/4 non-overlapping folds are positive, and >=2/3 fixed windows beat ACWI. No product/date/cost/timing/weight tuning after observation.','decision':'INDEPENDENT_INVESTABLE_REPRESENTATION_SUPPORTED' if pass_gate else 'INDEPENDENT_INVESTABLE_REPRESENTATION_NOT_SUPPORTED','scientific_consequence':('International momentum now has academic mechanism evidence plus an independent investable representation, despite P391 IMTM weakness. Preserve as a scoped survivor requiring genuine forward/implementation evidence, not product tuning.' if pass_gate else 'The independent investable representation also fails the fixed gate. Preserve academic mechanism evidence, but close the current ETF implementation search rather than cycling products or windows.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p407_idmo_international_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'opportunity_windows_beaten':opp,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))
