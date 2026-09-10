import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['MTUM','IWB','SPY']; W={'2014':'2014-01-01','2018':'2018-01-01','2022':'2022-01-01'}; B=10; BLOCK=6; N=5000; RNG=np.random.default_rng(244)
def cagr(r):
 q=np.asarray(r,float); return float(np.prod(1+q)**(12/len(q))-1)
def cost(r):
 q=np.asarray(r,float).copy(); f=B/10000
 if len(q): q[0]-=f; q[-1]-=f
 return q
def boot(d):
 arr=d[A].to_numpy(float); n=len(arr); di=[]; ds=[]
 for _ in range(N):
  idx=[]
  while len(idx)<n:
   s=int(RNG.integers(0,max(n-BLOCK+1,1))); idx.extend(range(s,min(s+BLOCK,n)))
  z=arr[np.array(idx[:n])]; di.append(cagr(cost(z[:,0]))-cagr(cost(z[:,1]))); ds.append(cagr(cost(z[:,0]))-cagr(cost(z[:,2])))
 return {'rows':n,'actual_vs_iwb':cagr(cost(arr[:,0]))-cagr(cost(arr[:,1])),'actual_vs_spy':cagr(cost(arr[:,0]))-cagr(cost(arr[:,2])),'iwb_p_nonpositive':float(np.mean(np.asarray(di)<=0)),'iwb_median':float(np.median(di)),'iwb_p05':float(np.quantile(di,.05)),'iwb_p95':float(np.quantile(di,.95)),'spy_p_nonpositive':float(np.mean(np.asarray(ds)<=0))}
r0=yf.download(A,start='2013-07-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; r=cl.dropna(how='any').resample('ME').last().pct_change().dropna(how='any'); t={k:boot(r.loc[pd.Timestamp(s):]) for k,s in W.items()}; ok=t['2014']['actual_vs_iwb']>0 and t['2014']['iwb_p_nonpositive']<=.10 and t['2022']['actual_vs_iwb']>0 and t['2022']['iwb_p_nonpositive']<=.20
out={'schema':'research.p244_mtum_block_bootstrap_r1','parent':'P238/P244','claim':'P238 positive aggregate MTUM-IWB excess survives a fixed serial-dependence-preserving bootstrap despite the failed 2018 chronology window','contract':{'candidate':'MTUM','matched_control':'IWB','opportunity_context':'SPY','windows':W,'cost_bps':B,'block_months':BLOCK,'samples':N,'seed':244,'no_window_fund_or_parameter_search':True},'tests':t,'decision':'P244_STATISTICAL_SUPPORT_WITH_CHRONOLOGY_CAVEAT' if ok else 'P244_NOT_SUPPORTED','limitations':['does not override P238 predeclared chronology failure','ETF proxy is not academic long-short momentum'],'boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p244_mtum_block_bootstrap_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
