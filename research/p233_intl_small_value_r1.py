import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['AVDV','VSS','IEFA','SPY']; W={'2020':'2020-01-01','2021':'2021-01-01','2022':'2022-01-01'}; B=10
def m(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); return {'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min())}
def c(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def ev(d):
 z={a:m(c(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:m(c(q[a])) for a in A}; fs.append({'fold':i,'vs_vss':mm['AVDV']['cagr']-mm['VSS']['cagr'],'vs_iefa':mm['AVDV']['cagr']-mm['IEFA']['cagr'],'vs_spy':mm['AVDV']['cagr']-mm['SPY']['cagr']})
 return {'metrics':z,'vs_vss':z['AVDV']['cagr']-z['VSS']['cagr'],'vs_iefa':z['AVDV']['cagr']-z['IEFA']['cagr'],'vs_spy':z['AVDV']['cagr']-z['SPY']['cagr'],'positive_vss_folds':sum(x['vs_vss']>0 for x in fs),'folds':fs}
r0=yf.download(A,start='2019-10-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); t={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; ok=all(t[k]['vs_vss']>0 for k in W) and t['2020']['positive_vss_folds']>=4 and t['2021']['positive_vss_folds']>=4; out={'schema':'research.p233_intl_small_value_r1','parent':'P233','contract':{'candidate':'AVDV','matched_control':'VSS','secondary_control':'IEFA','opportunity_context':'SPY','windows':W,'folds':5,'cost_bps':B,'fixed_test':True},'tests':t,'decision':'P233_SUPPORT' if ok else 'P233_NOT_SUPPORTED','boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p233_intl_small_value_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))