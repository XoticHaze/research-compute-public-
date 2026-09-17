from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']
ALL=TICKERS+['SPY']
COST=0.0025
START='2004-01-01'

def cagr(r):
    r=r.dropna()
    if len(r)<2:return float('nan')
    return float((1+r).prod()**(12/len(r))-1)
def sharpe(r):
    r=r.dropna()
    s=r.std(ddof=1)
    return float(np.sqrt(12)*r.mean()/s) if len(r)>1 and s>0 else float('nan')
def maxdd(r):
    x=(1+r.fillna(0)).cumprod(); return float((x/x.cummax()-1).min())

d=yf.download(ALL,start=START,auto_adjust=True,progress=False,threads=False)
if d.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d
close=close[ALL].dropna(how='all')
monthly=close.resample('ME').last().dropna()
ret=monthly.pct_change()
# Standard 12-to-1 cross-sectional momentum, frozen top-3. At month t use only month t-1 and older prices,
# then hold selected sectors during month t+1. This intentionally adds a full causal gap and forbids same-close use.
score=monthly.shift(1)/monthly.shift(12)-1
weights=pd.DataFrame(0.0,index=monthly.index,columns=TICKERS)
for dt,row in score[TICKERS].iterrows():
    if row.notna().sum()!=len(TICKERS): continue
    top=row.nlargest(3).index
    weights.loc[dt,top]=1/3
held=weights.shift(1).fillna(0)
turnover=0.5*held.diff().abs().sum(axis=1).fillna(held.abs().sum(axis=1))
strategy=(held*ret[TICKERS]).sum(axis=1)-COST*turnover
base_w=pd.DataFrame(1/len(TICKERS),index=monthly.index,columns=TICKERS)
base_turn=0.5*base_w.diff().abs().sum(axis=1).fillna(base_w.abs().sum(axis=1))
baseline=(base_w*ret[TICKERS]).sum(axis=1)-COST*base_turn
spy=ret['SPY'].copy()
valid=(held.sum(axis=1)>0)&strategy.notna()&baseline.notna()&spy.notna()
strategy=strategy[valid]; baseline=baseline[valid]; spy=spy[valid]; turnover=turnover[valid]

def window(start,end=None):
    s=strategy.loc[start:end]; b=baseline.reindex(s.index); q=spy.reindex(s.index)
    return {'start':str(s.index.min().date()) if len(s) else start,'end':str(s.index.max().date()) if len(s) else end,
            'months':int(len(s)),'strategy_cagr':cagr(s),'matched_cagr':cagr(b),'spy_cagr':cagr(q),
            'matched_excess_pp':100*(cagr(s)-cagr(b)),'spy_excess_pp':100*(cagr(s)-cagr(q)),
            'strategy_sharpe':sharpe(s),'matched_sharpe':sharpe(b),'strategy_max_drawdown':maxdd(s),'matched_max_drawdown':maxdd(b),
            'annualized_turnover':float(turnover.reindex(s.index).mean()*12)}
windows={k:window(v) for k,v in {'2010+':'2010-01-01','2015+':'2015-01-01','2020+':'2020-01-01'}.items()}
fold_bounds=[('2005-01-01','2008-12-31'),('2009-01-01','2012-12-31'),('2013-01-01','2016-12-31'),('2017-01-01','2020-12-31'),('2021-01-01',None)]
folds=[]
for a,b in fold_bounds:
    w=window(a,b); w['positive_matched']=bool(w['matched_excess_pp']>0); folds.append(w)
pos=sum(x['positive_matched'] for x in folds)
all_match=all(x['matched_excess_pp']>0 for x in windows.values())
spy_wins=sum(x['spy_excess_pp']>0 for x in windows.values())
pass_gate=all_match and pos>=4 and spy_wins>=2
out={'schema':'research.p383_sector_xsmom.v1','workload_id':'P383_SECTOR_XSMOM_R1','claim':'Prospectively fixed cross-sectional sector selection can add after-cost excess return versus owning the same sector universe equally, without tactical cash timing.','universe':TICKERS,'benchmark':'SPY','signal':'monthly 12-to-1 momentum using price[t-1]/price[t-12]-1','selection':'top 3 sectors equal weight','execution':'weights selected from lagged signal and applied one additional month later','cost_bps_one_way':25,'matched_control':'monthly equal-weight same 9-sector universe with identical turnover-cost convention','windows':windows,'folds':folds,'positive_matched_folds':pos,'spy_positive_windows':spy_wins,'decision_rule':'SUPPORTED only if matched excess CAGR >0 in 2010+/2015+/2020+, >=4/5 chronological folds positive versus matched control, and >=2/3 fixed windows beat SPY opportunity cost. No lookback/top-k/universe/cost/date tuning after observation.','decision':'SECTOR_XSMOM_SUPPORTED' if pass_gate else 'SECTOR_XSMOM_NOT_SUPPORTED','scientific_consequence':('Cross-sectional selection earns survivor status for orthogonal validation; no parameter tuning or portfolio authority follows.' if pass_gate else 'Reject this exact sector-selection formulation; preserve any passing dimensions, do not parameter-rescue, and rotate architecture.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p383_sector_xsmom_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_matched_folds':pos,'spy_positive_windows':spy_wins,'windows':{k:{'matched_excess_pp':round(v['matched_excess_pp'],3),'spy_excess_pp':round(v['spy_excess_pp'],3)} for k,v in windows.items()}},sort_keys=True))
