import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
A=['AVUV','IJR','IWM','SPY']; W={'2020':'2020-01-01','2021':'2021-01-01','2022':'2022-01-01'}; B=10
def m(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); return {'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min())}
def c(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def ev(d):
 z={a:m(c(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:m(c(q[a])) for a in A}; fs.append({'fold':i,'vs_ijr':mm['AVUV']['cagr']-mm['IJR']['cagr'],'vs_iwm':mm['AVUV']['cagr']-mm['IWM']['cagr'],'vs_spy':mm['AVUV']['cagr']-mm['SPY']['cagr']})
 return {'metrics':z,'vs_ijr':z['AVUV']['cagr']-z['IJR']['cagr'],'vs_iwm':z['AVUV']['cagr']-z['IWM']['cagr'],'vs_spy':z['AVUV']['cagr']-z['SPY']['cagr'],'positive_ijr_folds':sum(x['vs_ijr']>0 for x in fs),'folds':fs}
r0=yf.download(A,start='2019-10-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); t={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; ok=all(t[k]['vs_ijr']>0 for k in W) and t['2020']['positive_ijr_folds']>=4 and t['2020']['vs_spy']>0; out={'schema':'research.p228_smallcap_value_r1','parent':'P228','contract':{'candidate':'AVUV','controls':['IJR','IWM','SPY'],'windows':W,'folds':5,'cost_bps':B,'fixed_test':True},'tests':t,'decision':'P228_SUPPORT' if ok else 'P228_NOT_SUPPORTED','boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p228_smallcap_value_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))