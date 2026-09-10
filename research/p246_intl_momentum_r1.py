import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['IMTM','IEFA','ACWX','SPY']; W={'2016':'2016-01-01','2020':'2020-01-01','2022':'2022-01-01'}; B=10
def m(r):
 q=pd.Series(r).dropna(); e=(1+q).cumprod(); n=len(q); return {'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min())}
def c(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def ev(d):
 z={a:m(c(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:m(c(q[a])) for a in A}; fs.append({'fold':i,'vs_iefa':mm['IMTM']['cagr']-mm['IEFA']['cagr'],'vs_acwx':mm['IMTM']['cagr']-mm['ACWX']['cagr'],'vs_spy':mm['IMTM']['cagr']-mm['SPY']['cagr']})
 return {'metrics':z,'vs_iefa':z['IMTM']['cagr']-z['IEFA']['cagr'],'vs_acwx':z['IMTM']['cagr']-z['ACWX']['cagr'],'vs_spy':z['IMTM']['cagr']-z['SPY']['cagr'],'positive_iefa_folds':sum(x['vs_iefa']>0 for x in fs),'positive_acwx_folds':sum(x['vs_acwx']>0 for x in fs),'folds':fs}
r0=yf.download(A,start='2015-09-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; r=cl.dropna(how='any').resample('ME').last().pct_change().dropna(how='any'); t={k:ev(r.loc[pd.Timestamp(s):]) for k,s in W.items()}; ok=all(t[k]['vs_iefa']>0 and t[k]['vs_acwx']>0 for k in W) and t['2016']['positive_iefa_folds']>=4 and t['2016']['positive_acwx_folds']>=4
out={'schema':'research.p246_intl_momentum_r1','parent':'P246','claim':'fixed developed/ex-US momentum fund creates durable after-cost excess versus broad international controls','contract':{'candidate':'IMTM','matched_controls':['IEFA','ACWX'],'opportunity_context':'SPY','windows':W,'folds':5,'cost_bps':B,'fixed_test':True,'no_fund_window_or_parameter_search':True},'tests':t,'decision':'P246_SUPPORT' if ok else 'P246_NOT_SUPPORTED','limitations':['ETF is an implementable momentum proxy','SPY is opportunity context, not matched geography control'],'boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p246_intl_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
