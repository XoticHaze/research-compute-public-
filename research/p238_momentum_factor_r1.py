import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['MTUM','IWB','SPY']; W={'2014':'2014-01-01','2018':'2018-01-01','2022':'2022-01-01'}; B=10
def m(r):
 r=pd.Series(r).dropna(); eq=(1+r).cumprod(); n=len(r); return {'cagr':float(eq.iloc[-1]**(12/n)-1),'maxdd':float((eq/eq.cummax()-1).min())}
def c(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def ev(d):
 z={a:m(c(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:m(c(q[a])) for a in A}; fs.append({'fold':i,'vs_iwb':mm['MTUM']['cagr']-mm['IWB']['cagr'],'vs_spy':mm['MTUM']['cagr']-mm['SPY']['cagr']})
 return {'metrics':z,'vs_iwb':z['MTUM']['cagr']-z['IWB']['cagr'],'vs_spy':z['MTUM']['cagr']-z['SPY']['cagr'],'positive_iwb_folds':sum(x['vs_iwb']>0 for x in fs),'positive_spy_folds':sum(x['vs_spy']>0 for x in fs),'folds':fs}
r0=yf.download(A,start='2013-07-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); t={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; ok=all(t[k]['vs_iwb']>0 for k in W) and t['2014']['positive_iwb_folds']>=4; out={'schema':'research.p238_momentum_factor_r1','parent':'P238','claim':'fixed US cross-sectional momentum fund creates durable after-cost excess versus broad US equity control','contract':{'candidate':'MTUM','matched_control':'IWB','opportunity_context':'SPY','windows':W,'folds':5,'cost_bps':B,'fixed_test':True,'no_parameter_search':True},'tests':t,'decision':'P238_SUPPORT' if ok else 'P238_NOT_SUPPORTED','limitations':['ETF is an implementable factor proxy rather than academic long-short momentum','monthly endpoint representation'],'boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p238_momentum_factor_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))