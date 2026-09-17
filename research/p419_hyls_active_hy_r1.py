from __future__ import annotations
import json
from pathlib import Path
import pandas as pd, numpy as np, yfinance as yf
T=['HYLS','HYG','SPY']; COST=0.0025
x=yf.download(T,start='2013-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().dropna().pct_change().dropna()
def charge(s):
 y=s.copy()
 if len(y): y.iloc[0]-=COST; y.iloc[-1]-=COST
 return y
def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def sh(s):
 sd=s.std(ddof=1); return float(np.sqrt(12)*s.mean()/sd) if len(s)>1 and sd>0 else float('nan')
def dd(s):
 w=(1+s).cumprod(); return float((w/w.cummax()-1).min()) if len(s) else float('nan')
def ev(a,b=None):
 q=charge(r.HYLS.loc[a:b]); ctl=charge(r.HYG.reindex(q.index)); opp=charge(r.SPY.reindex(q.index))
 return {'months':len(q),'hyls_cagr':cagr(q),'hyg_cagr':cagr(ctl),'spy_cagr':cagr(opp),'matched_excess_pp':100*(cagr(q)-cagr(ctl)),'spy_excess_pp':100*(cagr(q)-cagr(opp)),'hyls_sharpe':sh(q),'hyg_sharpe':sh(ctl),'hyls_max_drawdown':dd(q),'hyg_max_drawdown':dd(ctl)}
windows={k:ev(v) for k,v in {'2014+':'2014-01-01','2018+':'2018-01-01','2020+':'2020-01-01','2022+':'2022-01-01'}.items()}
folds=[]
for a,b in [('2014-01-01','2015-12-31'),('2016-01-01','2017-12-31'),('2018-01-01','2019-12-31'),('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]:
 z=ev(a,b); z['positive_matched_excess']=z['matched_excess_pp']>0; folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds)
passed=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=4
out={'schema':'research.p419_hyls_active_high_yield.v1','workload_id':'P419_HYLS_ACTIVE_HIGH_YIELD_R1','parent':'ACTIVE_HIGH_YIELD_SELECTION','claim':'A prospectively fixed active high-yield fund representation via HYLS can deliver durable after-cost excess over passive HYG without timing or parameter search. SPY is opportunity-cost context, not the matched credit control.','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'decision_rule':'SUPPORTED only if HYLS beats HYG after fixed endpoint friction in 2014+/2018+/2020+/2022+ and >=4/6 chronology folds are positive. SPY opportunity context is reported separately. No manager/product/date/cost/timing rescue.','decision':'ACTIVE_HIGH_YIELD_SELECTION_SUPPORTED' if passed else 'ACTIVE_HIGH_YIELD_SELECTION_NOT_SUPPORTED','scientific_consequence':('Active high-yield selection earns initial scoped survivor status requiring orthogonal validation.' if passed else 'Reject this exact HYLS-vs-HYG durable-alpha claim; preserve any passing regimes but do not cycle managers/products/windows to rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p419_hyls_active_hy_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))