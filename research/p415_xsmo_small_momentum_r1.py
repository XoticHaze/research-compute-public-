from __future__ import annotations
import json
from pathlib import Path
import pandas as pd, numpy as np, yfinance as yf
T=['XSMO','IJR','SPY']; COST=0.0025
x=yf.download(T,start='2018-01-01',auto_adjust=True,progress=False,threads=False)
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
 q=charge(r.XSMO.loc[a:b]); ctl=charge(r.IJR.reindex(q.index)); opp=charge(r.SPY.reindex(q.index))
 return {'months':len(q),'xsmo_cagr':cagr(q),'ijr_cagr':cagr(ctl),'spy_cagr':cagr(opp),'matched_excess_pp':100*(cagr(q)-cagr(ctl)),'spy_excess_pp':100*(cagr(q)-cagr(opp)),'xsmo_sharpe':sh(q),'ijr_sharpe':sh(ctl),'xsmo_max_drawdown':dd(q),'ijr_max_drawdown':dd(ctl)}
windows={k:ev(v) for k,v in {'2019+':'2019-01-01','2021+':'2021-01-01','2023+':'2023-01-01'}.items()}
folds=[]
for a,b in [('2019-01-01','2020-12-31'),('2021-01-01','2022-12-31'),('2023-01-01','2024-12-31'),('2025-01-01',None)]:
 z=ev(a,b); z['positive_matched_excess']=z['matched_excess_pp']>0; folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds); opp=sum(z['spy_excess_pp']>0 for z in windows.values())
passed=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=3
out={'schema':'research.p415_xsmo_small_momentum.v1','workload_id':'P415_XSMO_SMALL_MOMENTUM_R1','parent':'SMALL_CAP_MOMENTUM_TRANSPORT','claim':'A prospectively fixed small-cap momentum fund representation via XSMO can transport the previously supported momentum mechanism by delivering durable after-cost excess over IJR without timing or parameter search. SPY is opportunity-cost context, not the matched factor control.','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'opportunity_windows_beaten':opp,'decision_rule':'TRANSPORT_SUPPORTED only if XSMO beats IJR after fixed endpoint friction in 2019+/2021+/2023+ and >=3/4 chronology folds are positive. SPY opportunity context is reported but not required because this is a size-matched transport claim. No product/date/cost/timing rescue.','decision':'SMALL_CAP_MOMENTUM_TRANSPORT_SUPPORTED' if passed else 'SMALL_CAP_MOMENTUM_TRANSPORT_NOT_SUPPORTED','scientific_consequence':('Momentum mechanism transports to the small-cap fund representation in the tested scope; require orthogonal robustness before broadening.' if passed else 'Do not broaden the supported momentum mechanism to this exact small-cap representation; preserve existing SPMO/XMMO evidence and classify this as transport failure only.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p415_xsmo_small_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'opportunity_windows_beaten':opp,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))