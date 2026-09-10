from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p445_quality_factor_alpha_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
T=['QUAL','SPHQ','SPY']; COST=.0025; WINDOWS=['2015-01-01','2020-01-01','2022-01-01']; BLOCKS=[('2015-01-01','2017-12-31'),('2018-01-01','2020-12-31'),('2021-01-01','2023-12-31'),('2024-01-01','2026-09-10')]
p=yf.download(T,start='2014-01-01',end='2026-09-11',auto_adjust=True,progress=False)['Close'].dropna(); r=p.pct_change(fill_method=None).dropna()
def cagr(x):
 x=x.dropna().copy();
 if len(x)<2:return None
 x.iloc[0]-=COST; x.iloc[-1]-=COST; return float((1+x).prod()**(252/len(x))-1)
def metrics(sym,a,b=None):
 z=r.loc[a:b,[sym,'SPY']].dropna(); y=z[sym]; x=z.SPY; beta=float(np.cov(y,x,ddof=1)[0,1]/np.var(x,ddof=1)); alpha=float((y.mean()-beta*x.mean())*252); return {'days':len(z),'fund_cagr':cagr(y),'spy_cagr':cagr(x),'excess_cagr':cagr(y)-cagr(x),'beta':beta,'beta_adjusted_alpha_annual':alpha}
rows={s:{'windows':[metrics(s,a) for a in WINDOWS],'blocks':[metrics(s,a,b) for a,b in BLOCKS]} for s in ['QUAL','SPHQ']}
def pass_sym(v): return all(x['excess_cagr']>0 and x['beta_adjusted_alpha_annual']>0 for x in v['windows']) and sum(x['beta_adjusted_alpha_annual']>0 for x in v['blocks'])>=3
passed=all(pass_sym(v) for v in rows.values())
out={'schema':'research.p445_quality_factor_alpha_r1.v1','workload_id':'P445_QUALITY_FACTOR_ALPHA_R1','parent':'QUALITY_FACTOR_FUND_ALPHA','claim':'A broad U.S. quality-factor sleeve should produce durable after-cost excess and positive beta-adjusted alpha versus SPY across two independent ETF implementations rather than relying on one wrapper.','contract':{'funds':['QUAL','SPHQ'],'matched_control':'SPY','fixed_windows':WINDOWS,'chronology_blocks':BLOCKS,'endpoint_cost_bps_each':25,'acceptance':'Both funds require positive after-cost excess CAGR and positive beta-adjusted annual alpha in all three fixed windows, plus positive beta-adjusted alpha in at least 3/4 chronology blocks. No product/date/cost rescue.'},'results':rows,'decision':'QUALITY_FACTOR_ALPHA_SUPPORTED' if passed else 'QUALITY_FACTOR_ALPHA_NOT_SUPPORTED','scientific_consequence':('Quality factor qualifies as an independent alpha candidate for further robustness/capital-efficiency work.' if passed else 'This exact two-implementation quality-factor alpha formulation is rejected; do not rescue with nearby products, dates, costs, or thresholds.'),'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'results':rows},sort_keys=True))
