from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p533_turn_of_month_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
COST=.0010
WINDOWS={'2005_plus':'2005-01-03','2010_plus':'2010-01-04','2015_plus':'2015-01-02'}
BLOCKS={'2005_2009':('2005-01-03','2009-12-31'),'2010_2014':('2010-01-04','2014-12-31'),'2015_2019':('2015-01-02','2019-12-31'),'2020_plus':('2020-01-02',None)}
px=yf.download('SPY',start='2004-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
close=px['Close'] if 'Close' in px else px
if isinstance(close,pd.DataFrame): close=close.iloc[:,0]
r=close.pct_change(fill_method=None).dropna()
df=pd.DataFrame({'SPY':r})
df['month']=df.index.to_period('M')
df['ord']=df.groupby('month').cumcount()+1
df['n']=df.groupby('month')['SPY'].transform('size')
# Canonical turn-of-month definition: last trading day of a month plus first three trading days of the next month.
df['signal']=((df['ord']<=3)|(df['ord']==df['n'])).astype(float)
df['turnover']=df['signal'].diff().abs().fillna(df['signal'])
df['strategy_net']=df['signal']*df['SPY']-df['turnover']*COST

def perf(x):
 rr=x.to_numpy(); wealth=np.cumprod(1+rr); yrs=len(rr)/252; peak=np.maximum.accumulate(wealth); dd=wealth/peak-1
 av=float(np.std(rr,ddof=1)*np.sqrt(252)) if len(rr)>1 else 0; ar=float(np.mean(rr)*252)
 return {'cagr':float(wealth[-1]**(1/yrs)-1),'max_drawdown':float(dd.min()),'annualized_vol':av,'simple_sharpe':ar/av if av>0 else None}

def stats(start,end=None):
 x=df.loc[df.index>=pd.Timestamp(start)].copy(); x=x if end is None else x.loc[x.index<=pd.Timestamp(end)].copy(); exp=float(x['signal'].mean()); x['matched_static']=exp*x['SPY']; ps,pm,pp=perf(x['strategy_net']),perf(x['matched_static']),perf(x['SPY']); return {'days':len(x),'mean_exposure':exp,'strategy':ps,'matched_static_exposure':pm,'spy':pp,'excess_vs_matched_cagr':ps['cagr']-pm['cagr'],'excess_vs_spy_cagr':ps['cagr']-pp['cagr'],'drawdown_improvement_vs_spy':ps['max_drawdown']-pp['max_drawdown'],'sharpe_improvement_vs_matched':ps['simple_sharpe']-pm['simple_sharpe']}
w={k:stats(v) for k,v in WINDOWS.items()}; b={k:stats(a,z) for k,(a,z) in BLOCKS.items()}; s={'positive_vs_matched_windows':sum(v['excess_vs_matched_cagr']>0 for v in w.values()),'positive_vs_matched_blocks':sum(v['excess_vs_matched_cagr']>0 for v in b.values()),'sharpe_improved_windows':sum(v['sharpe_improvement_vs_matched']>0 for v in w.values()),'drawdown_improved_windows':sum(v['drawdown_improvement_vs_spy']>0 for v in w.values())}; ok=s['positive_vs_matched_windows']==3 and s['positive_vs_matched_blocks']>=3 and s['sharpe_improved_windows']==3; d='TURN_OF_MONTH_ALPHA_SUPPORTED' if ok else 'TURN_OF_MONTH_ALPHA_NOT_SUPPORTED'; out={'schema':'research.p533_turn_of_month_r1.v1','workload_id':'P533_TURN_OF_MONTH_R1','parent':'EQUITY_CALENDAR_SEASONALITY','claim':'The canonical last-trading-day plus first-three-trading-days turn-of-month window can add after-cost return versus a static SPY exposure matched to its capital usage.','contract':{'asset':'SPY','signal':'last trading day of each month plus first three trading days of each month','cost_bps_per_exposure_turnover':10,'windows':WINDOWS,'blocks':BLOCKS,'support_rule':'positive excess vs exposure-matched SPY 3/3 fixed windows and >=3/4 chronology blocks, Sharpe improvement 3/3','no_calendar_window_asset_date_cost_or_weight_search':True},'windows':w,'blocks':b,'summary':s,'decision':d,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}; OUT.write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps({'decision':d,'summary':s,'windows':{k:{'vs_matched_pp':round(v['excess_vs_matched_cagr']*100,3),'vs_spy_pp':round(v['excess_vs_spy_cagr']*100,3),'dd_pp':round(v['drawdown_improvement_vs_spy']*100,3),'mean_exp':round(v['mean_exposure'],3),'sharpe_delta':round(v['sharpe_improvement_vs_matched'],3)} for k,v in w.items()},'blocks_vs_matched_pp':{k:round(v['excess_vs_matched_cagr']*100,3) for k,v in b.items()}},sort_keys=True))