from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd, yfinance as yf
T=['HEFA','IEFA','SPY']; EP=.0025
x=yf.download(T,start='2014-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
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
 q=r.loc[a:b]; s=stats(q.HEFA); ctl=stats(q.IEFA); opp=stats(q.SPY)
 return {'hefa':s,'iefa_control':ctl,'spy_opportunity':opp,'matched_excess_pp':100*(s['cagr']-ctl['cagr']),'spy_excess_pp':100*(s['cagr']-opp['cagr']),'sharpe_delta':s['sharpe']-ctl['sharpe'],'maxdd_delta':s['max_drawdown']-ctl['max_drawdown']}
windows={k:ev(v) for k,v in {'2015+':'2015-01-01','2020+':'2020-01-01','2022+':'2022-01-01'}.items()}
blocks={k:ev(a,b) for k,(a,b) in {'2015_2017':('2015-01-01','2017-12-31'),'2018_2020':('2018-01-01','2020-12-31'),'2021_2023':('2021-01-01','2023-12-31'),'2024_plus':('2024-01-01',None)}.items()}
pos=sum(z['matched_excess_pp']>0 for z in blocks.values()); supported=all(z['matched_excess_pp']>0 for z in windows.values()) and pos>=3
decision='DEVELOPED_EXUS_CURRENCY_HEDGE_SUPPORTED' if supported else 'DEVELOPED_EXUS_CURRENCY_HEDGE_NOT_DURABLY_SUPPORTED'
out={'schema':'research.p426_hefa_currency_hedge_r1.v1','workload_id':'P426_HEFA_CURRENCY_HEDGE_R1','claim':'A prospectively fixed currency-hedged developed ex-U.S. equity fund representation (HEFA) can deliver durable after-cost excess over unhedged IEFA, with SPY opportunity cost reported separately.','cost_bps_each_endpoint':25,'windows':windows,'chronology_blocks':blocks,'positive_blocks':pos,'decision_rule':'SUPPORTED only if HEFA-IEFA after-cost CAGR excess is positive in 2015+/2020+/2022+ and >=3/4 fixed chronology blocks are positive. SPY opportunity cost cannot rescue the claim.','decision':decision,'scientific_consequence':('Currency hedging earns initial scoped mechanism support requiring an independent currency-regime/implementation adjudicator.' if supported else 'Do not treat currency hedging as a durable ex-U.S. alpha source; preserve any passing currency regimes as conditional evidence and rotate without hedge-ratio, date, or product rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p426_hefa_currency_hedge_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'positive_blocks':pos,'windows':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()},'blocks':{k:round(v['matched_excess_pp'],3) for k,v in blocks.items()}},sort_keys=True))
