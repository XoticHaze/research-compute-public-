from __future__ import annotations
import json
from pathlib import Path
import pandas as pd, numpy as np, yfinance as yf
T=['USMV','SPY','BIL']; COST=0.0025
x=yf.download(T,start='2012-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().dropna().pct_change().dropna()
def charge(s):
 y=s.copy()
 if len(y): y.iloc[0]-=COST; y.iloc[-1]-=COST
 return y
def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def ev(a,b=None):
 z=r.loc[a:b]; u=charge(z.USMV); m=charge(z.SPY); rf=charge(z.BIL)
 ux=u-rf; mx=m-rf
 beta=float(np.cov(ux,mx,ddof=1)[0,1]/np.var(mx,ddof=1)) if len(z)>2 and np.var(mx,ddof=1)>0 else float('nan')
 alpha=float((ux-beta*mx).mean()*12) if len(z)>2 else float('nan')
 return {'months':len(z),'usmv_cagr':cagr(u),'spy_cagr':cagr(m),'bil_cagr':cagr(rf),'spy_opportunity_excess_pp':100*(cagr(u)-cagr(m)),'beta_to_spy_excess':beta,'annualized_jensen_alpha_pp':100*alpha}
full=ev('2013-01-01')
blocks=[ev('2013-01-01','2016-12-31'),ev('2017-01-01','2020-12-31'),ev('2021-01-01')]
pos=sum(z['annualized_jensen_alpha_pp']>0 for z in blocks)
passed=full['annualized_jensen_alpha_pp']>0 and full['beta_to_spy_excess']<0.9 and pos>=2
out={'schema':'research.p422_usmv_beta_alpha.v1','workload_id':'P422_USMV_BETA_ALPHA_R1','parent':'US_MINIMUM_VOLATILITY_BETA_ADJUSTED','claim':'A prospectively fixed U.S. minimum-volatility fund representation via USMV can exhibit durable positive after-cost beta-adjusted alpha relative to SPY excess returns over BIL, rather than being judged only on raw SPY outperformance.','cost_bps_each_endpoint':25,'full':full,'blocks':blocks,'positive_alpha_blocks':pos,'decision_rule':'SUPPORTED only if full 2013+ annualized Jensen alpha is positive after fixed endpoint friction, full beta is <0.9 as required by the low-vol representation, and >=2/3 fixed chronology blocks have positive alpha. Raw USMV-SPY return difference is reported as opportunity cost and is not optimized away. No product/date/beta-window/cost rescue.','decision':'US_MINIMUM_VOLATILITY_BETA_ADJUSTED_SUPPORTED' if passed else 'US_MINIMUM_VOLATILITY_BETA_ADJUSTED_NOT_SUPPORTED','scientific_consequence':('U.S. minimum-volatility earns scoped beta-adjusted survivor status; raw SPY opportunity cost remains a separate portfolio question.' if passed else 'Do not support this exact USMV beta-adjusted alpha claim; preserve any passing blocks and do not tune beta windows/products to rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p422_usmv_beta_alpha_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'full_alpha_pp':round(full['annualized_jensen_alpha_pp'],3),'full_beta':round(full['beta_to_spy_excess'],3),'spy_opportunity_pp':round(full['spy_opportunity_excess_pp'],3),'block_alpha_pp':[round(z['annualized_jensen_alpha_pp'],3) for z in blocks]},sort_keys=True))