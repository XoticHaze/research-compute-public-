import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['IMTM','IEFA','SPY']; W={'2016':'2016-01-01','2020':'2020-01-01','2022':'2022-01-01'}; B=10
def m(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); return {'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min())}
def c(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def ev(d):
 z={a:m(c(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:m(c(q[a])) for a in A}; fs.append({'fold':i,'vs_iefa':mm['IMTM']['cagr']-mm['IEFA']['cagr'],'vs_spy':mm['IMTM']['cagr']-mm['SPY']['cagr']})
 return {'metrics':z,'vs_iefa':z['IMTM']['cagr']-z['IEFA']['cagr'],'vs_spy':z['IMTM']['cagr']-z['SPY']['cagr'],'positive_iefa_folds':sum(x['vs_iefa']>0 for x in fs),'folds':fs}
r0=yf.download(A,start='2015-07-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); t={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; ok=all(t[k]['vs_iefa']>0 for k in W) and t['2016']['positive_iefa_folds']>=4 and t['2020']['positive_iefa_folds']>=4; out={'schema':'research.p229_intl_momentum_r1','parent':'P229','contract':{'candidate':'IMTM','matched_control':'IEFA','opportunity_context':'SPY','windows':W,'folds':5,'cost_bps':B,'fixed_test':True},'tests':t,'decision':'P229_SUPPORT' if ok else 'P229_NOT_SUPPORTED','boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p229_intl_momentum_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))