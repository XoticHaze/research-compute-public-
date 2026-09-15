from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
OUT=Path('research/artifacts/p482_convertible_convexity_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
FUNDS=['CWB','ICVT']; EQ='SPY'; CASH='BIL'; COST=.0010
WINDOWS=['2016-01-31','2020-01-31']; BLOCKS=[('2016-01-31','2019-12-31'),('2020-01-31','2022-12-31'),('2023-01-31','2026-08-31')]
px=yf.download(FUNDS+[EQ,CASH],start='2015-01-01',end='2026-09-11',auto_adjust=True,progress=False)['Close'].resample('ME').last().dropna();r=px.pct_change(fill_method=None).dropna()
def cagr(x):return float((1+x).prod()**(12/len(x))-1)
def dd(x):z=(1+x).cumprod();return float((z/z.cummax()-1).min())
def calc(a,b=None):
 z=r.loc[a:b];out={}
 for f in FUNDS:
  y=z[f].copy();eq=z[EQ].copy();cash=z[CASH].copy();y.iloc[0]-=COST;eq.iloc[0]-=COST;cash.iloc[0]-=COST
  yx=(y-cash).to_numpy(); xx=(eq-cash).to_numpy(); X=np.column_stack([np.ones(len(z)),xx]);coef=np.linalg.lstsq(X,yx,rcond=None)[0]
  out[f]={'months':len(z),'fund_cagr':cagr(y),'cash_cagr':cagr(cash),'spy_cagr':cagr(eq),'excess_vs_cash':cagr(y)-cagr(cash),'opportunity_cost_vs_spy':cagr(y)-cagr(eq),'cash_adjusted_equity_alpha_annual':float(coef[0]*12),'equity_excess_beta':float(coef[1]),'max_drawdown':dd(y)}
 return out
wins=[{'start':a,'results':calc(a)} for a in WINDOWS];blocks=[{'start':a,'end':b,'results':calc(a,b)} for a,b in BLOCKS]
passes={f:all(x['results'][f]['excess_vs_cash']>0 and x['results'][f]['cash_adjusted_equity_alpha_annual']>0 for x in wins) and sum(x['results'][f]['cash_adjusted_equity_alpha_annual']>0 for x in blocks)>=2 for f in FUNDS};supported=all(passes.values())
out={'schema':'research.p482_convertible_convexity_r2.v1','workload_id':'P482_CONVERTIBLE_CONVEXITY_R2','parent':'NEW_PORTFOLIO_ROLE_OR_CORE_RETURN_CHALLENGER','claim':'Convertible-bond convexity should create durable return beyond cash and positive alpha after controlling equity excess return over cash, replicated across CWB and ICVT.','method_correction':'R1 joint raw SPY+BIL regression produced unstable low-variance cash coefficients and implausible intercepts. R2 uses the standard excess-return form (fund-cash)=alpha+beta*(SPY-cash), with funds, dates, costs and acceptance signs unchanged.','contract':{'funds':FUNDS,'matched_return_baseline':CASH,'equity_control':EQ,'fixed_windows':WINDOWS,'chronology_blocks':BLOCKS,'entry_cost_bps_each_series':10,'acceptance':'Both implementations positive excess vs cash and positive cash-adjusted equity annual alpha in both fixed windows, plus positive alpha in >=2/3 chronology blocks. No leverage, timing, wrapper, date or threshold rescue.'},'windows':wins,'blocks':blocks,'implementation_pass':passes,'decision':'CONVERTIBLE_CONVEXITY_SUPPORTED' if supported else 'CONVERTIBLE_CONVEXITY_NOT_SUPPORTED','scientific_consequence':'Qualify convertible convexity for independent complementarity/opportunity-cost falsification.' if supported else 'Reject exact convertible-convexity role; do not rescue with nearby wrappers or timing.','boundaries':{'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':out['decision'],'passes':passes,'windows':wins,'blocks':blocks},sort_keys=True))