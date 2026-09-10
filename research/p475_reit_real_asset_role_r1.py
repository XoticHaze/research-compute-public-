from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p475_reit_real_asset_role_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
FUNDS=['VNQ','IYR']; BENCH='SPY'; COST=.0010
WINDOWS=['2005-01-31','2012-01-31','2020-01-31']
BLOCKS=[('2005-01-31','2009-12-31'),('2010-01-31','2014-12-31'),('2015-01-31','2019-12-31'),('2020-01-31','2026-08-31')]
px=yf.download(FUNDS+[BENCH],start='2004-01-01',end='2026-09-11',auto_adjust=True,progress=False)['Close'].resample('ME').last().dropna()
r=px.pct_change(fill_method=None).dropna()

def cagr(x): return float((1+x).prod()**(12/len(x))-1) if len(x) else None

def dd(x):
    z=(1+x).cumprod(); return float((z/z.cummax()-1).min()) if len(z) else None

def beta_alpha(y,x):
    X=np.column_stack([np.ones(len(x)),x.to_numpy()]); b=np.linalg.lstsq(X,y.to_numpy(),rcond=None)[0]
    return {'beta':float(b[1]),'alpha_annual':float(b[0]*12)}

def period(a,b=None):
    z=r.loc[a:b]; out={}
    for f in FUNDS:
        y=z[f].copy(); x=z[BENCH].copy()
        if len(y): y.iloc[0]-=COST
        if len(x): x.iloc[0]-=COST
        ba=beta_alpha(y,x)
        out[f]={'months':int(len(y)),'fund_cagr':cagr(y),'spy_cagr':cagr(x),'excess_vs_spy':cagr(y)-cagr(x),'max_drawdown':dd(y),'spy_max_drawdown':dd(x),**ba}
    return out

windows=[{'start':a,'results':period(a)} for a in WINDOWS]
blocks=[{'start':a,'end':b,'results':period(a,b)} for a,b in BLOCKS]
passes={}
for f in FUNDS:
    passes[f]=all(w['results'][f]['excess_vs_spy']>0 and w['results'][f]['alpha_annual']>0 for w in windows) and sum(b['results'][f]['excess_vs_spy']>0 and b['results'][f]['alpha_annual']>0 for b in blocks)>=3
supported=all(passes.values())
out={
 'schema':'research.p475_reit_real_asset_role_r1.v1','workload_id':'P475_REIT_REAL_ASSET_ROLE_R1','parent':'NEW_PORTFOLIO_ROLE_OR_CORE_RETURN_CHALLENGER',
 'claimed_portfolio_role':'Listed real-estate equity as an inflation-sensitive real-asset return sleeve, distinct from CLO credit, managed futures, international factors, low-vol equity and industry-state selection.',
 'claim':'A broad listed-REIT mechanism should create durable fund-net-of-expense excess versus SPY and positive beta-adjusted alpha across independent implementations, not merely provide thematic inflation exposure.',
 'contract':{'implementations':FUNDS,'benchmark':BENCH,'price_basis':'Yahoo adjusted close; ETF expenses/distributions embedded','entry_cost_bps_each_leg':10,'fixed_windows':WINDOWS,'chronology_blocks':BLOCKS,'acceptance':'Both VNQ and IYR require positive excess_vs_spy and positive beta-adjusted annual alpha in every fixed window and >=3/4 chronology blocks. No rate filter, leverage, sector carveout, wrapper substitution or date rescue.'},
 'windows':windows,'blocks':blocks,'implementation_pass':passes,'decision':'REIT_REAL_ASSET_ALPHA_SUPPORTED' if supported else 'REIT_REAL_ASSET_ALPHA_NOT_SUPPORTED',
 'scientific_consequence':'Qualify listed real estate for direct portfolio-complementarity and inflation-regime opportunity-cost testing.' if supported else 'Reject broad listed real estate as a durable alpha role under this exact contract; any inflation or diversification benefit remains contextual and does not justify return-role admission.',
 'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'strategy_spec_mutation':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'implementation_pass':passes,'windows':windows,'blocks':blocks},sort_keys=True))
