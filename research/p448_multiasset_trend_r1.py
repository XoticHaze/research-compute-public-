from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p448_multiasset_trend_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
RISK=['SPY','IEF','GLD','DBC']; ALL=RISK+['BIL']; COST=.0010; WINDOWS=['2010-01-31','2016-01-31','2020-01-31']; BLOCKS=[('2010-01-31','2013-12-31'),('2014-01-31','2017-12-31'),('2018-01-31','2021-12-31'),('2022-01-31','2026-08-31')]
p=yf.download(ALL,start='2008-01-01',end='2026-09-11',auto_adjust=True,progress=False)['Close'].resample('ME').last().dropna(); r=p.pct_change(fill_method=None); mom=p[RISK].pct_change(12).shift(1)
w=pd.DataFrame(0.0,index=p.index,columns=ALL)
for d in p.index:
 sig=mom.loc[d].dropna(); pos=[s for s in RISK if s in sig and sig[s]>0]
 if pos:
  for s in pos:w.loc[d,s]=1/len(pos)
 else:w.loc[d,'BIL']=1.0
turn=w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1)); strat=(w.shift(1)*r).sum(axis=1)-COST*turn.shift(1).fillna(0); static=r[RISK].mean(axis=1); q=pd.DataFrame({'strategy':strat,'static':static}).dropna()
def cagr(x): return float((1+x).prod()**(12/len(x))-1)
def dd(x): z=(1+x).cumprod(); return float((z/z.cummax()-1).min())
def m(a,b=None):
 z=q.loc[a:b]; return {'months':len(z),'strategy_cagr':cagr(z.strategy),'static_cagr':cagr(z.static),'excess_cagr':cagr(z.strategy)-cagr(z.static),'strategy_max_drawdown':dd(z.strategy),'static_max_drawdown':dd(z.static),'strategy_vol':float(z.strategy.std()*np.sqrt(12)),'static_vol':float(z.static.std()*np.sqrt(12))}
win=[m(a) for a in WINDOWS]; blocks=[m(a,b) for a,b in BLOCKS]; passed=all(x['excess_cagr']>0 for x in win) and sum(x['excess_cagr']>0 for x in blocks)>=3 and all(x['strategy_max_drawdown']>=x['static_max_drawdown'] for x in win)
out={'schema':'research.p448_multiasset_trend_r1.v1','workload_id':'P448_MULTI_ASSET_TREND_R1','parent':'MULTI_ASSET_TREND_FUND_MODEL','claim':'A fixed monthly 12-month absolute-trend model across equities, Treasuries, gold and broad commodities, with cash fallback, should produce durable after-cost excess versus the matched static equal-weight asset basket while reducing drawdown.','contract':{'assets':RISK,'cash':'BIL','signal':'prior completed 12-month total return > 0','allocation':'equal weight among positive-trend risky assets; 100% BIL if none','rebalance':'monthly','turnover_cost_bps':10,'fixed_windows':WINDOWS,'chronology_blocks':BLOCKS,'acceptance':'Positive excess CAGR in all fixed windows, positive excess in >=3/4 chronology blocks, and no worse max drawdown in all fixed windows. No lookback/asset/cost rescue.'},'windows':win,'blocks':blocks,'decision':'MULTI_ASSET_TREND_SUPPORTED' if passed else 'MULTI_ASSET_TREND_NOT_SUPPORTED','scientific_consequence':('Promote to orthogonal robustness and opportunity-cost testing; no allocation authority.' if passed else 'Reject exact multi-asset trend formulation; no nearby lookback/asset/cost rescue.'),'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}; OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'windows':win,'blocks':blocks},sort_keys=True))
