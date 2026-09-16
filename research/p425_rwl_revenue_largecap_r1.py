from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd, yfinance as yf
T=['RWL','SPY','QQQ']; EP=.0025
x=yf.download(T,start='2009-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().dropna().pct_change(fill_method=None).dropna()
def ep(s):
 y=s.copy()
 if len(y): y.iloc[0]-=EP; y.iloc[-1]-=EP
 return y
def stats(s):
 q=ep(s.dropna()); n=len(q)
 if n<2:return {'months':n,'cagr':None,'sharpe':None,'max_drawdown':None}
 w=(1+q).cumprod(); vol=q.std(ddof=1)*(12**.5); ann=q.mean()*12
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(ann/vol) if vol else None,'max_drawdown':float((w/w.cummax()-1).min())}
def ev(a,b=None):
 q=r.loc[a:b]; s=stats(q.RWL); ctl=stats(q.SPY); opp=stats(q.QQQ)
 return {'rwl':s,'spy_control':ctl,'qqq_opportunity':opp,'matched_excess_pp':100*(s['cagr']-ctl['cagr']),'qqq_excess_pp':100*(s['cagr']-opp['cagr']),'sharpe_delta_vs_spy':s['sharpe']-ctl['sharpe'],'maxdd_delta_vs_spy':s['max_drawdown']-ctl['max_drawdown']}
windows={k:ev(v) for k,v in {'2010+':'2010-01-01','2015+':'2015-01-01','2020+':'2020-01-01'}.items()}
blocks={k:ev(a,b) for k,(a,b) in {'2010_2014':('2010-01-01','2014-12-31'),'2015_2019':('2015-01-01','2019-12-31'),'2020_plus':('2020-01-01',None)}.items()}
pos=sum(z['matched_excess_pp']>0 for z in blocks.values()); supported=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=2
decision='REVENUE_WEIGHTED_LARGE_CAP_SUPPORTED' if supported else 'REVENUE_WEIGHTED_LARGE_CAP_NOT_SUPPORTED'
out={'schema':'research.p425_rwl_revenue_largecap_r1.v1','workload_id':'P425_RWL_REVENUE_LARGECAP_R1','claim':'A prospectively fixed revenue-weighted U.S. large-cap representation (RWL) can deliver durable after-cost excess over SPY, with QQQ opportunity cost reported separately.','cost_bps_each_endpoint':25,'windows':windows,'chronology_blocks':blocks,'positive_blocks':pos,'decision_rule':'SUPPORTED only if RWL-SPY after-cost CAGR excess is positive in 2010+/2015+/2020+ and at least 2/3 fixed chronology blocks are positive. QQQ is opportunity context only and cannot rescue the claim.','decision':decision,'scientific_consequence':('Revenue weighting earns large-cap transport support; combine only with independent P424 evidence when judging the family.' if supported else 'Reject this exact large-cap revenue-weighting claim; preserve any passing eras and independently judge P424 small-cap evidence without product/date/threshold rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p425_rwl_revenue_largecap_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'positive_blocks':pos,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()},'qqq_excess':{k:round(v['qqq_excess_pp'],3) for k,v in windows.items()}},sort_keys=True))
