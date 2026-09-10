from __future__ import annotations
import json
from pathlib import Path
import pandas as pd, numpy as np, yfinance as yf
T=['BTAL','BIL','SPY']; COST=0.0025
x=yf.download(T,start='2011-01-01',auto_adjust=True,progress=False,threads=False)
if x.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=x['Close'] if isinstance(x.columns,pd.MultiIndex) else x
r=c[T].resample('ME').last().dropna().pct_change().dropna()
def charge(s):
 y=s.copy()
 if len(y): y.iloc[0]-=COST; y.iloc[-1]-=COST
 return y
def cagr(s): return float((1+s).prod()**(12/len(s))-1) if len(s) else float('nan')
def sh(s):
 sd=s.std(ddof=1); return float(np.sqrt(12)*s.mean()/sd) if len(s)>1 and sd>0 else float('nan')
def dd(s):
 w=(1+s).cumprod(); return float((w/w.cummax()-1).min()) if len(s) else float('nan')
def ev(a,b=None):
 q=charge(r.BTAL.loc[a:b]); ctl=charge(r.BIL.reindex(q.index)); opp=charge(r.SPY.reindex(q.index))
 return {'months':len(q),'btal_cagr':cagr(q),'bil_cagr':cagr(ctl),'spy_cagr':cagr(opp),'cash_excess_pp':100*(cagr(q)-cagr(ctl)),'spy_excess_pp':100*(cagr(q)-cagr(opp)),'btal_sharpe':sh(q),'bil_sharpe':sh(ctl),'btal_max_drawdown':dd(q),'bil_max_drawdown':dd(ctl)}
windows={k:ev(v) for k,v in {'2012+':'2012-01-01','2016+':'2016-01-01','2020+':'2020-01-01','2022+':'2022-01-01'}.items()}
folds=[]
for a,b in [('2012-01-01','2013-12-31'),('2014-01-01','2015-12-31'),('2016-01-01','2017-12-31'),('2018-01-01','2019-12-31'),('2020-01-01','2021-12-31'),('2022-01-01','2023-12-31'),('2024-01-01',None)]:
 z=ev(a,b); z['positive_cash_excess']=z['cash_excess_pp']>0; folds.append(z)
pos=sum(z['positive_cash_excess'] for z in folds)
passed=all(z['cash_excess_pp']>0 for z in windows.values()) and pos>=5 and windows['2012+']['btal_sharpe']>0
out={'schema':'research.p418_btal_antibeta.v1','workload_id':'P418_BTAL_ANTIBETA_R1','parent':'EQUITY_MARKET_NEUTRAL_ANTI_BETA','claim':'A prospectively fixed equity market-neutral anti-beta fund representation via BTAL can deliver durable after-cost absolute excess over Treasury-bill cash (BIL), with SPY opportunity-cost context, without timing or parameter search.','cost_bps_each_endpoint':25,'windows':windows,'folds':folds,'positive_folds':pos,'decision_rule':'SUPPORTED only if BTAL beats BIL after fixed endpoint friction in 2012+/2016+/2020+/2022+, >=5/7 chronology folds have positive cash excess, and full-history Sharpe is positive. SPY is opportunity context, not a matched market-neutral control. No product/date/cost/timing rescue.','decision':'EQUITY_MARKET_NEUTRAL_ANTI_BETA_SUPPORTED' if passed else 'EQUITY_MARKET_NEUTRAL_ANTI_BETA_NOT_SUPPORTED','scientific_consequence':('Anti-beta earns initial scoped absolute-return survivor status requiring orthogonal validation and complementarity testing.' if passed else 'Reject this exact BTAL durable absolute-return claim while preserving any passing regimes; do not cycle market-neutral products or windows to rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p418_btal_antibeta_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive_folds':pos,'windows':{k:round(v['cash_excess_pp'],3) for k,v in windows.items()},'full_sharpe':round(windows['2012+']['btal_sharpe'],3)},sort_keys=True))