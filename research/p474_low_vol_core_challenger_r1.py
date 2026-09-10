from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p474_low_vol_core_challenger_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
FUNDS=['SPLV','USMV']; BENCH='SPY'; COST=.0010
WINDOWS=['2012-01-31','2016-01-31','2020-01-31']
BLOCKS=[('2012-01-31','2015-12-31'),('2016-01-31','2019-12-31'),('2020-01-31','2022-12-31'),('2023-01-31','2026-08-31')]
px=yf.download(FUNDS+[BENCH],start='2011-01-01',end='2026-09-11',auto_adjust=True,progress=False)['Close'].resample('ME').last().dropna()
r=px.pct_change(fill_method=None).dropna()

def cagr(x):
    if len(x)==0:return None
    return float((1+x).prod()**(12/len(x))-1)

def dd(x):
    z=(1+x).cumprod(); return float((z/z.cummax()-1).min()) if len(z) else None

def beta_alpha(y,x):
    if len(y)<12:return {'beta':None,'alpha_annual':None}
    X=np.column_stack([np.ones(len(x)),x.to_numpy()]); coef=np.linalg.lstsq(X,y.to_numpy(),rcond=None)[0]
    return {'beta':float(coef[1]),'alpha_annual':float(coef[0]*12)}

def period(a,b=None):
    z=r.loc[a:b].copy(); out={}
    for f in FUNDS:
        y=z[f].copy(); x=z[BENCH].copy()
        if len(y): y.iloc[0]-=COST
        if len(x): x.iloc[0]-=COST
        ba=beta_alpha(y,x)
        out[f]={'months':int(len(y)),'fund_cagr':cagr(y),'spy_cagr':cagr(x),'excess_vs_spy':cagr(y)-cagr(x),'max_drawdown':dd(y),'spy_max_drawdown':dd(x),**ba}
    return out

windows=[{'start':a,'results':period(a)} for a in WINDOWS]
blocks=[{'start':a,'end':b,'results':period(a,b)} for a,b in BLOCKS]

def impl_pass(f):
    win_ok=all(w['results'][f]['excess_vs_spy']>0 and w['results'][f]['alpha_annual']>0 for w in windows)
    block_ok=sum(b['results'][f]['excess_vs_spy']>0 and b['results'][f]['alpha_annual']>0 for b in blocks)>=3
    return win_ok and block_ok
passes={f:impl_pass(f) for f in FUNDS}; supported=all(passes.values())
out={
 'schema':'research.p474_low_vol_core_challenger_r1.v1',
 'workload_id':'P474_LOW_VOL_CORE_CHALLENGER_R1',
 'parent':'NEW_PORTFOLIO_ROLE_OR_CORE_RETURN_CHALLENGER',
 'claimed_portfolio_role':'Fully invested U.S. equity core-return challenger using low-volatility stock selection, distinct from defensive credit, managed futures, international factor, and industry-state sleeves.',
 'claim':'A low-volatility equity selection mechanism should create durable fund-net-of-expense, after-entry-cost excess versus SPY and positive beta-adjusted alpha rather than merely reducing beta.',
 'contract':{
   'implementations':FUNDS,'benchmark':BENCH,'price_basis':'Yahoo adjusted close; ETF expenses/distributions embedded','entry_cost_bps_each_leg':10,
   'fixed_windows':WINDOWS,'chronology_blocks':BLOCKS,
   'acceptance':'Both SPLV and USMV require positive excess_vs_spy and positive beta-adjusted annual alpha in every fixed window and >=3/4 chronology blocks. No fund substitution, timing filter, weighting, or threshold rescue.'
 },
 'windows':windows,'blocks':blocks,'implementation_pass':passes,
 'decision':'LOW_VOL_CORE_ALPHA_SUPPORTED' if supported else 'LOW_VOL_CORE_ALPHA_NOT_SUPPORTED',
 'scientific_consequence':'Qualify low-volatility equity as a distinct core-return challenger for deeper complementarity/opportunity-cost testing.' if supported else 'Reject this exact low-volatility equity core-alpha mechanism; preserve any drawdown benefit only as risk-shaping context and do not rescue with nearby wrappers or timing filters.',
 'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'strategy_spec_mutation':False,'runtime':False,'broker':False,'live_trading':False}
}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'implementation_pass':passes,'windows':windows,'blocks':blocks},sort_keys=True))
