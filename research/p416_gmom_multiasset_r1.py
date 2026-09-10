from __future__ import annotations
import json
from pathlib import Path
import pandas as pd, numpy as np, yfinance as yf
T=['GMOM','AOR','ACWI']; COST=0.0025
x=yf.download(T,start='2015-01-01',auto_adjust=True,progress=False,threads=False)
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
 q=charge(r.GMOM.loc[a:b]); ctl=charge(r.AOR.reindex(q.index)); opp=charge(r.ACWI.reindex(q.index))
 return {'months':len(q),'gmom_cagr':cagr(q),'aor_cagr':cagr(ctl),'acwi_cagr':cagr(opp),'matched_excess_pp':100*(cagr(q)-cagr(ctl)),'acwi_excess_pp':100*(cagr(q)-cagr(opp)),'gmom_sharpe':sh(q),'aor_sharpe':sh(ctl),'gmom_max_drawdown':dd(q),'aor_max_drawdown':dd(ctl)}
windows={k:ev(v) for k,v in {'2016+':'2016-01-01','2020+':'2020-01-01','2022+':'2022-01-01'}.items()}
folds=[]
for a,b in [('2016-01-01','2017-12-31'),('2018-01-01','2019-12-31'),('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]:
 z=ev(a,b); z['positive_matched_excess']=z['matched_excess_pp']>0; folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds); opp=sum(z['acwi_excess_pp']>0 for z in windows.values())
passed=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=4
out={'schema':'research.p416_gmom_multiasset.v1','workload_id':'P416_GMOM_MULTI_ASSET_R1','parent':'GLOBAL_MULTI_ASSET_MOMENTUM','claim':'A prospectively fixed global multi-asset momentum fund representation via GMOM can deliver durable after-cost excess over AOR as a diversified static-allocation control, with ACWI opportunity-cost context, without timing or parameter search.','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'opportunity_windows_beaten':opp,'decision_rule':'SUPPORTED only if GMOM beats AOR after fixed endpoint friction in 2016+/2020+/2022+ and >=4/5 chronology folds are positive. ACWI opportunity context is reported separately. No product/date/cost/timing rescue.','decision':'GLOBAL_MULTI_ASSET_MOMENTUM_SUPPORTED' if passed else 'GLOBAL_MULTI_ASSET_MOMENTUM_NOT_SUPPORTED','scientific_consequence':('Global multi-asset momentum earns initial scoped survivor status requiring orthogonal validation.' if passed else 'Reject this exact GMOM versus AOR durable-alpha claim; preserve any passing regimes but do not cycle tactical-allocation products or windows to rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p416_gmom_multiasset_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'opportunity_windows_beaten':opp,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))