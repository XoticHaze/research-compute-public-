import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['AVUV','IJR','SPY']; W={'2020':'2020-01-01','2021':'2021-01-01','2022':'2022-01-01'}; B=10; BLOCK=6; N=5000; SEED=232
def cost(r):
 q=np.array(r,float).copy(); f=B/10000
 if len(q): q[0]-=f; q[-1]-=f
 return q
def cagr(r): return float(np.prod(1+np.asarray(r,float))**(12/len(r))-1)
def boot(d):
 rng=np.random.default_rng(SEED); arr=d[A].to_numpy(float); n=len(arr); starts=np.arange(max(n-BLOCK+1,1)); xi=[]; xs=[]
 for _ in range(N):
  rows=[]
  while len(rows)<n:
   s=int(rng.choice(starts)); rows.extend(arr[s:min(s+BLOCK,n)])
  z=np.asarray(rows[:n]); xi.append(cagr(cost(z[:,0]))-cagr(cost(z[:,1]))); xs.append(cagr(cost(z[:,0]))-cagr(cost(z[:,2])))
 actual_ijr=cagr(cost(arr[:,0]))-cagr(cost(arr[:,1])); actual_spy=cagr(cost(arr[:,0]))-cagr(cost(arr[:,2])); return {'rows':n,'actual_vs_ijr':actual_ijr,'actual_vs_spy':actual_spy,'p_nonpositive_vs_ijr':float(np.mean(np.asarray(xi)<=0)),'p_nonpositive_vs_spy':float(np.mean(np.asarray(xs)<=0)),'bootstrap_median_vs_ijr':float(np.median(xi)),'bootstrap_p05_vs_ijr':float(np.quantile(xi,.05)),'bootstrap_p95_vs_ijr':float(np.quantile(xi,.95))}
r0=yf.download(A,start='2019-10-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); t={k:boot(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; ok=all(t[k]['actual_vs_ijr']>0 and t[k]['p_nonpositive_vs_ijr']<=.10 for k in W); out={'schema':'research.p232_avuv_block_bootstrap_r1','parent':'P232','contract':{'candidate':'AVUV','matched_control':'IJR','opportunity_context':'SPY','windows':W,'cost_bps':B,'moving_block_months':BLOCK,'samples':N,'seed':SEED,'gate':'positive actual AVUV-IJR and <=10% moving-block probability of nonpositive matched excess in every window','fixed_test':True},'tests':t,'decision':'P232_SUPPORT' if ok else 'P232_NOT_SUPPORTED','boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p232_avuv_block_bootstrap_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))