from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd, yfinance as yf
T=['USCI','DBC','SPY']; EP=.0025
x=yf.download(T,start='2011-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
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
 w=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12); ann=q.mean()*12
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(ann/vol) if vol else None,'max_drawdown':float((w/w.cummax()-1).min())}
def ev(a,b=None):
 q=r.loc[a:b]; s=stats(q.USCI); ctl=stats(q.DBC); opp=stats(q.SPY)
 return {'usci':s,'dbc_control':ctl,'spy_opportunity':opp,'matched_excess_pp':100*(s['cagr']-ctl['cagr']),'spy_excess_pp':100*(s['cagr']-opp['cagr']),'sharpe_delta_vs_dbc':s['sharpe']-ctl['sharpe'],'maxdd_delta_vs_dbc':s['max_drawdown']-ctl['max_drawdown']}
windows={k:ev(v) for k,v in {'2012+':'2012-01-01','2016+':'2016-01-01','2020+':'2020-01-01'}.items()}
blocks={k:ev(a,b) for k,(a,b) in {'2012_2015':('2012-01-01','2015-12-31'),'2016_2019':('2016-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_plus':('2023-01-01',None)}.items()}
pos=sum(v['matched_excess_pp']>0 for v in blocks.values()); supported=all(v['matched_excess_pp']>0 for v in windows.values()) and pos>=3
decision='COMMODITY_CROSS_SECTIONAL_SELECTION_SUPPORTED' if supported else 'COMMODITY_CROSS_SECTIONAL_SELECTION_NOT_SUPPORTED'
out={'schema':'research.p431_usci_commodity_selection_r1.v1','workload_id':'P431_USCI_COMMODITY_SELECTION_R1','parent':'COMMODITY_CROSS_SECTIONAL_SELECTION','claim':'A prospectively fixed systematic commodity selection representation (USCI) can deliver durable after-cost excess over broad long-commodity control DBC, with SPY opportunity cost reported separately. This is a within-commodity selection claim, distinct from managed-futures absolute trend following.','cost_bps_each_endpoint':25,'windows':windows,'chronology_blocks':blocks,'positive_blocks':pos,'decision_rule':'SUPPORTED only if USCI-DBC after-cost CAGR excess is positive in 2012+/2016+/2020+ and >=3/4 fixed chronology blocks are positive. SPY is opportunity context only.','decision':decision,'scientific_consequence':('Commodity cross-sectional/carry-selection earns initial scoped survivor status requiring an independent mechanism/transport test.' if supported else 'Reject this exact USCI-versus-DBC durable commodity-selection claim; preserve any passing eras but do not rescue via another commodity-selection product, dates, or thresholds.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p431_usci_commodity_selection_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'positive_blocks':pos,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()},'blocks':{k:round(v['matched_excess_pp'],3) for k,v in blocks.items()}},sort_keys=True))
