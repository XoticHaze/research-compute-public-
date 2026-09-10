from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT=Path('research/artifacts/p476_fx_carry_role_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
CARRY='DBV'; CASH='BIL'; EQUITY='SPY'; COST=.0010
WINDOWS=['2008-01-31','2012-01-31','2020-01-31']
BLOCKS=[('2008-01-31','2011-12-31'),('2012-01-31','2015-12-31'),('2016-01-31','2019-12-31'),('2020-01-31','2026-08-31')]
px=yf.download([CARRY,CASH,EQUITY],start='2007-01-01',end='2026-09-11',auto_adjust=True,progress=False)['Close'].resample('ME').last().dropna()
r=px.pct_change(fill_method=None).dropna()

def cagr(x): return float((1+x).prod()**(12/len(x))-1) if len(x) else None

def dd(x):
    z=(1+x).cumprod(); return float((z/z.cummax()-1).min()) if len(z) else None

def period(a,b=None):
    z=r.loc[a:b].copy(); carry=z[CARRY].copy(); cash=z[CASH].copy(); eq=z[EQUITY].copy()
    if len(carry): carry.iloc[0]-=COST
    if len(cash): cash.iloc[0]-=COST
    if len(eq): eq.iloc[0]-=COST
    excess=carry-cash
    corr=float(carry.corr(eq)) if len(carry)>2 else None
    X=np.column_stack([np.ones(len(eq)),eq.to_numpy()]); coef=np.linalg.lstsq(X,carry.to_numpy(),rcond=None)[0] if len(eq)>2 else [np.nan,np.nan]
    return {'months':int(len(carry)),'carry_cagr':cagr(carry),'cash_cagr':cagr(cash),'spy_cagr':cagr(eq),'excess_vs_cash':cagr(carry)-cagr(cash),'opportunity_cost_vs_spy':cagr(carry)-cagr(eq),'max_drawdown':dd(carry),'spy_correlation':corr,'spy_beta':float(coef[1]) if len(eq)>2 else None,'spy_alpha_annual':float(coef[0]*12) if len(eq)>2 else None,'positive_excess_month_fraction':float((excess>0).mean()) if len(excess) else None}

windows=[{'start':a,**period(a)} for a in WINDOWS]
blocks=[{'start':a,'end':b,**period(a,b)} for a,b in BLOCKS]
passed=all(x['excess_vs_cash']>0 for x in windows) and sum(x['excess_vs_cash']>0 for x in blocks)>=3 and all(abs(x['spy_correlation'])<0.5 for x in windows)
out={
 'schema':'research.p476_fx_carry_role_r1.v1','workload_id':'P476_FX_CARRY_ROLE_R1','parent':'NEW_PORTFOLIO_ROLE_OR_CORE_RETURN_CHALLENGER',
 'claimed_portfolio_role':'G10 currency carry return sleeve harvesting cross-currency interest-rate differentials, distinct from managed-futures trend, equity factors, credit, real estate, and industry-state selection.',
 'claim':'A transparent G10 currency-carry implementation should earn durable after-cost excess over cash across chronology while remaining meaningfully decorrelated from U.S. equities.',
 'contract':{'implementation':CARRY,'matched_return_baseline':CASH,'opportunity_cost_control':EQUITY,'price_basis':'Yahoo adjusted close; fund expenses/distributions embedded','entry_cost_bps_each_series':10,'fixed_windows':WINDOWS,'chronology_blocks':BLOCKS,'acceptance':'Positive excess versus BIL in all fixed windows and >=3/4 chronology blocks, with |SPY monthly return correlation| < 0.5 in all fixed windows. SPY opportunity cost and alpha are reported, not optimized. No date, signal, leverage, currency-set, threshold, or wrapper rescue.'},
 'windows':windows,'blocks':blocks,'decision':'FX_CARRY_ROLE_SUPPORTED' if passed else 'FX_CARRY_ROLE_NOT_SUPPORTED',
 'scientific_consequence':'Qualify exact G10 currency carry mechanism for independent replication and incremental portfolio opportunity-cost/complementarity testing.' if passed else 'Reject this exact G10 currency carry mechanism as a durable return role; do not rescue with nearby currency wrappers, leverage, timing, or date changes.',
 'boundaries':{'portfolio_ranking':False,'allocation_authority':False,'strategy_spec_mutation':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'windows':windows,'blocks':blocks},sort_keys=True))
