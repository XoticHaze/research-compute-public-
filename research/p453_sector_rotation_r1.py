from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p453_sector_rotation_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
SECT=['XLB','XLE','XLF','XLI','XLK','XLP','XLU','XLV','XLY']; COST=.0010; TOP=3; LB=6; WINDOWS=['2010-01-31','2016-01-31','2020-01-31']; BLOCKS=[('2010-01-31','2013-12-31'),('2014-01-31','2017-12-31'),('2018-01-31','2021-12-31'),('2022-01-31','2026-08-31')]
p=yf.download(SECT+['SPY'],start='2008-01-01',end='2026-09-11',auto_adjust=True,progress=False)['Close'].resample('ME').last().dropna(); r=p.pct_change(fill_method=None); mom=p[SECT].pct_change(LB).shift(1); w=pd.DataFrame(0.,index=p.index,columns=SECT)
for d in p.index:
 s=mom.loc[d].dropna().sort_values(ascending=False).head(TOP).index
 if len(s)==TOP:w.loc[d,s]=1/TOP
turn=w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1)); strat=(w.shift(1)*r[SECT]).sum(axis=1)-COST*turn.shift(1).fillna(0); equal=r[SECT].mean(axis=1); q=pd.DataFrame({'strategy':strat,'spy':r.SPY,'equal_sector':equal}).dropna()
def cagr(x):return float((1+x).prod()**(12/len(x))-1)
def dd(x):z=(1+x).cumprod();return float((z/z.cummax()-1).min())
def m(a,b=None):
 z=q.loc[a:b]; return {'months':len(z),'strategy_cagr':cagr(z.strategy),'spy_cagr':cagr(z.spy),'equal_sector_cagr':cagr(z.equal_sector),'excess_vs_spy':cagr(z.strategy)-cagr(z.spy),'excess_vs_equal_sector':cagr(z.strategy)-cagr(z.equal_sector),'strategy_max_drawdown':dd(z.strategy),'spy_max_drawdown':dd(z.spy)}
win=[m(a) for a in WINDOWS]; blocks=[m(a,b) for a,b in BLOCKS]; passed=all(x['excess_vs_spy']>0 and x['excess_vs_equal_sector']>0 for x in win) and sum(x['excess_vs_spy']>0 and x['excess_vs_equal_sector']>0 for x in blocks)>=3
out={'schema':'research.p453_sector_rotation_r1.v1','workload_id':'P453_SECTOR_ROTATION_R1','parent':'SECTOR_SELECTION_FUND_MODEL','claim':'A causal monthly industry-selection layer using prior six-month sector momentum and top-3 equal weighting should create durable after-cost excess versus both SPY and a static equal-sector basket.','contract':{'sectors':SECT,'signal':'prior completed 6-month total return','selection':'top 3 sectors monthly, equal weight','turnover_cost_bps':10,'matched_controls':['SPY','static equal-weight sector basket'],'fixed_windows':WINDOWS,'chronology_blocks':BLOCKS,'acceptance':'Positive excess versus both controls in all fixed windows and >=3/4 chronology blocks. No lookback/top-k/sector/cost rescue.'},'windows':win,'blocks':blocks,'decision':'SECTOR_ROTATION_ALPHA_SUPPORTED' if passed else 'SECTOR_ROTATION_ALPHA_NOT_SUPPORTED','scientific_consequence':('Sector-selection layer qualifies for orthogonal regime/turnover robustness and eventual ticker-within-sector research, without allocation authority.' if passed else 'Reject exact sector-selection model; no nearby lookback/top-k/cost rescue.'),'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}; OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'windows':win,'blocks':blocks},sort_keys=True))
