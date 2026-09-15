from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p451_exus_value_alpha_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
PAIRS={'EFV':'EFA','FNDF':'VEA'}; COST=.0025; WINDOWS=['2014-01-01','2018-01-01','2022-01-01']; BLOCKS=[('2014-01-01','2016-12-31'),('2017-01-01','2019-12-31'),('2020-01-01','2022-12-31'),('2023-01-01','2026-09-10')]
p=yf.download(list(PAIRS)+list(PAIRS.values()),start='2013-01-01',end='2026-09-11',auto_adjust=True,progress=False)['Close'].dropna(); r=p.pct_change(fill_method=None).dropna()
def cagr(x):
 x=x.copy(); x.iloc[0]-=COST; x.iloc[-1]-=COST; return float((1+x).prod()**(252/len(x))-1)
def m(s,c,a,b=None):
 z=r.loc[a:b,[s,c]].dropna(); y=z[s]; x=z[c]; beta=float(np.cov(y,x,ddof=1)[0,1]/np.var(x,ddof=1)); alpha=float((y.mean()-beta*x.mean())*252); return {'days':len(z),'fund_cagr':cagr(y),'control_cagr':cagr(x),'excess_cagr':cagr(y)-cagr(x),'beta':beta,'beta_adjusted_alpha_annual':alpha}
res={s:{'control':c,'windows':[m(s,c,a) for a in WINDOWS],'blocks':[m(s,c,a,b) for a,b in BLOCKS]} for s,c in PAIRS.items()}
def ok(v):return all(x['excess_cagr']>0 and x['beta_adjusted_alpha_annual']>0 for x in v['windows']) and sum(x['beta_adjusted_alpha_annual']>0 for x in v['blocks'])>=3
passed=all(ok(v) for v in res.values()); out={'schema':'research.p451_exus_value_alpha_r1.v1','workload_id':'P451_EXUS_VALUE_ALPHA_R1','parent':'DEVELOPED_EXUS_VALUE_FACTOR_ALPHA','claim':'Developed ex-US value should create durable after-cost excess and beta-adjusted alpha versus matched broad developed ex-US controls across two independent implementations.','contract':{'pairs':PAIRS,'fixed_windows':WINDOWS,'chronology_blocks':BLOCKS,'endpoint_cost_bps_each':25,'acceptance':'Both value implementations positive excess and beta-adjusted alpha in all fixed windows and positive alpha in >=3/4 chronology blocks. No rescue.'},'results':res,'decision':'EXUS_VALUE_ALPHA_SUPPORTED' if passed else 'EXUS_VALUE_ALPHA_NOT_SUPPORTED','scientific_consequence':('Developed ex-US value qualifies for independent regime/currency interaction robustness.' if passed else 'Reject exact developed ex-US value alpha formulation; no nearby wrapper/date/cost rescue.'),'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}; OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'results':res},sort_keys=True))
