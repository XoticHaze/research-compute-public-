from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
T=['FTLS','SPY','BIL']; EP=.0025
x=yf.download(T,start='2015-01-01',end='2026-09-11',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().dropna().pct_change(fill_method=None).dropna()
def ep(s):
 y=s.copy()
 if len(y): y.iloc[0]-=EP; y.iloc[-1]-=EP
 return y
def stats(s):
 q=ep(s.dropna()); n=len(q)
 if n<3:return {'months':n,'cagr':None,'sharpe':None,'max_drawdown':None}
 w=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12); ann=q.mean()*12
 return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(ann/vol) if vol else None,'max_drawdown':float((w/w.cummax()-1).min())}
def reg(q):
 y=q.FTLS-q.BIL; z=q.SPY-q.BIL
 X=np.column_stack([np.ones(len(q)),z.values]); a,b=np.linalg.lstsq(X,y.values,rcond=None)[0]
 return {'months':len(q),'beta':float(b),'alpha_pp_annual':float(1200*a)}
def ev(a,b=None):
 q=r.loc[a:b].dropna(); s=stats(q.FTLS); spy=stats(q.SPY); rr=reg(q)
 return {'ftls':s,'spy_opportunity':spy,'regression':rr,'spy_cagr_opportunity_pp':100*(s['cagr']-spy['cagr']),'maxdd_improvement_vs_spy_pp':100*(s['max_drawdown']-spy['max_drawdown'])}
windows={k:ev(v) for k,v in {'2016+':'2016-01-01','2020+':'2020-01-01','2022+':'2022-01-01'}.items()}
blocks={k:ev(a,b) for k,(a,b) in {'2016_2018':('2016-01-01','2018-12-31'),'2019_2021':('2019-01-01','2021-12-31'),'2022_2024':('2022-01-01','2024-12-31'),'2025_plus':('2025-01-01',None)}.items()}
pos=sum(z['regression']['alpha_pp_annual']>0 for z in blocks.values()); supported=all(z['regression']['alpha_pp_annual']>0 for z in windows.values()) and pos>=3
decision='LONG_SHORT_EQUITY_BETA_ADJUSTED_ALPHA_SUPPORTED' if supported else 'LONG_SHORT_EQUITY_BETA_ADJUSTED_ALPHA_NOT_SUPPORTED'
out={'schema':'research.p432_ftls_longshort_alpha_r1.v1','workload_id':'P432_FTLS_LONGSHORT_ALPHA_R1','parent':'LONG_SHORT_EQUITY_ALPHA','claim':'A prospectively fixed long/short equity fund representation (FTLS) can deliver durable after-cost beta-adjusted alpha relative to SPY excess over BIL; raw SPY opportunity cost and drawdown are reported separately so lower beta cannot itself count as alpha.','cost_bps_each_endpoint':25,'windows':windows,'chronology_blocks':blocks,'positive_alpha_blocks':pos,'decision_rule':'SUPPORTED only if annualized Jensen alpha is positive in 2016+/2020+/2022+ and >=3/4 fixed chronology blocks are positive. No manager/product/date/beta/cost rescue.','decision':decision,'scientific_consequence':('Long/short equity earns initial scoped beta-adjusted alpha support requiring an independent implementation or residual-source test.' if supported else 'Reject this exact FTLS long/short beta-adjusted alpha claim while preserving any passing eras; do not rescue with another long/short manager, dates, beta model, or thresholds.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p432_ftls_longshort_alpha_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'positive_alpha_blocks':pos,'window_alpha_pp':{k:round(v['regression']['alpha_pp_annual'],3) for k,v in windows.items()},'block_alpha_pp':{k:round(v['regression']['alpha_pp_annual'],3) for k,v in blocks.items()},'betas':{k:round(v['regression']['beta'],3) for k,v in windows.items()}},sort_keys=True))
