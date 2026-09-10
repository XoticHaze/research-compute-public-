import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['AVES','IEMG','VWO','SPY']; W={'2022':'2022-01-01','2023':'2023-01-01','2024':'2024-01-01'}; B=10
def m(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); return {'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min())}
def c(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def ev(d):
 z={a:m(c(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:m(c(q[a])) for a in A}; fs.append({'fold':i,'vs_iemg':mm['AVES']['cagr']-mm['IEMG']['cagr'],'vs_vwo':mm['AVES']['cagr']-mm['VWO']['cagr'],'vs_spy':mm['AVES']['cagr']-mm['SPY']['cagr']})
 return {'metrics':z,'vs_iemg':z['AVES']['cagr']-z['IEMG']['cagr'],'vs_vwo':z['AVES']['cagr']-z['VWO']['cagr'],'vs_spy':z['AVES']['cagr']-z['SPY']['cagr'],'positive_iemg_folds':sum(x['vs_iemg']>0 for x in fs),'folds':fs}
r0=yf.download(A,start='2021-09-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); t={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; ok=all(t[k]['vs_iemg']>0 for k in W) and t['2022']['positive_iemg_folds']>=4 and t['2023']['positive_iemg_folds']>=4; out={'schema':'research.p235_em_value_transport_r1','parent':'P235','claim':'small-value factor transport to emerging markets using fixed AVES versus matched broad-EM controls','contract':{'candidate':'AVES','matched_control':'IEMG','secondary_control':'VWO','opportunity_context':'SPY','windows':W,'folds':5,'cost_bps':B,'fixed_test':True,'no_parameter_search':True},'tests':t,'decision':'P235_SUPPORT' if ok else 'P235_NOT_SUPPORTED','limitations':['short live history since AVES inception','fund implementation includes manager-specific portfolio construction'],'boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p235_em_value_transport_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))