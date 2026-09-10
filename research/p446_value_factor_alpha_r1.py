from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p446_value_factor_alpha_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
FUNDS=['VTV','IWD']; COST=.0025; WINDOWS=['2010-01-01','2016-01-01','2020-01-01']; BLOCKS=[('2010-01-01','2013-12-31'),('2014-01-01','2017-12-31'),('2018-01-01','2021-12-31'),('2022-01-01','2026-09-10')]
p=yf.download(FUNDS+['SPY'],start='2009-01-01',end='2026-09-11',auto_adjust=True,progress=False)['Close'].dropna(); r=p.pct_change(fill_method=None).dropna()
def cagr(x):
 x=x.dropna().copy(); x.iloc[0]-=COST; x.iloc[-1]-=COST; return float((1+x).prod()**(252/len(x))-1)
def m(s,a,b=None):
 z=r.loc[a:b,[s,'SPY']].dropna(); y=z[s]; x=z.SPY; beta=float(np.cov(y,x,ddof=1)[0,1]/np.var(x,ddof=1)); alpha=float((y.mean()-beta*x.mean())*252); return {'days':len(z),'fund_cagr':cagr(y),'spy_cagr':cagr(x),'excess_cagr':cagr(y)-cagr(x),'beta':beta,'beta_adjusted_alpha_annual':alpha}
res={s:{'windows':[m(s,a) for a in WINDOWS],'blocks':[m(s,a,b) for a,b in BLOCKS]} for s in FUNDS}
def ok(v):return all(x['excess_cagr']>0 and x['beta_adjusted_alpha_annual']>0 for x in v['windows']) and sum(x['beta_adjusted_alpha_annual']>0 for x in v['blocks'])>=3
passed=all(ok(v) for v in res.values()); out={'schema':'research.p446_value_factor_alpha_r1.v1','workload_id':'P446_VALUE_FACTOR_ALPHA_R1','parent':'US_VALUE_FACTOR_FUND_ALPHA','claim':'A broad U.S. value-factor sleeve should create durable after-cost excess and beta-adjusted alpha versus SPY across independent VTV and IWD implementations.','contract':{'funds':FUNDS,'matched_control':'SPY','fixed_windows':WINDOWS,'chronology_blocks':BLOCKS,'endpoint_cost_bps_each':25,'acceptance':'Both implementations positive after-cost excess and beta-adjusted alpha in all fixed windows and beta-adjusted alpha positive in >=3/4 chronology blocks. No rescue.'},'results':res,'decision':'VALUE_FACTOR_ALPHA_SUPPORTED' if passed else 'VALUE_FACTOR_ALPHA_NOT_SUPPORTED','scientific_consequence':('Value factor qualifies for further robustness/capital-efficiency work.' if passed else 'Reject this exact broad-value fund alpha formulation; no nearby wrapper/date/cost rescue.'),'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}; OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'results':res},sort_keys=True))
