from __future__ import annotations
import json
from pathlib import Path
import pandas as pd, numpy as np, yfinance as yf
T=['IQLT','EFA','ACWI']; COST=0.0025
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
 q=charge(r.IQLT.loc[a:b]); ctl=charge(r.EFA.reindex(q.index)); opp=charge(r.ACWI.reindex(q.index))
 return {'months':len(q),'iqlt_cagr':cagr(q),'efa_cagr':cagr(ctl),'acwi_cagr':cagr(opp),'matched_excess_pp':100*(cagr(q)-cagr(ctl)),'acwi_excess_pp':100*(cagr(q)-cagr(opp)),'iqlt_sharpe':sh(q),'efa_sharpe':sh(ctl),'iqlt_max_drawdown':dd(q),'efa_max_drawdown':dd(ctl)}
windows={k:ev(v) for k,v in {'2016+':'2016-01-01','2020+':'2020-01-01','2022+':'2022-01-01'}.items()}
folds=[]
for a,b in [('2016-01-01','2017-12-31'),('2018-01-01','2019-12-31'),('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]:
 z=ev(a,b); z['positive_matched_excess']=z['matched_excess_pp']>0; folds.append(z)
pos=sum(z['positive_matched_excess'] for z in folds); opp=sum(z['acwi_excess_pp']>0 for z in windows.values())
passed=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=4 and opp>=2
out={'schema':'research.p413_international_quality.v1','workload_id':'P413_INTERNATIONAL_QUALITY_R1','parent':'INTERNATIONAL_QUALITY','claim':'A prospectively fixed developed-market ex-US quality fund representation via IQLT can deliver durable after-cost excess over EFA, with ACWI opportunity-cost context, without timing or parameter search.','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'opportunity_windows_beaten':opp,'decision_rule':'SUPPORTED only if IQLT beats EFA after fixed endpoint friction in 2016+/2020+/2022+, >=4/5 chronology folds are positive, and >=2/3 windows beat ACWI. No product/date/cost/timing rescue.','decision':'INTERNATIONAL_QUALITY_SUPPORTED' if passed else 'INTERNATIONAL_QUALITY_NOT_SUPPORTED','scientific_consequence':('International quality earns initial scoped survivor status requiring orthogonal validation.' if passed else 'Reject this exact international-quality fund alpha claim; preserve any passing dimensions but do not cycle products or windows to rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p413_international_quality_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'opportunity_windows_beaten':opp,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))
