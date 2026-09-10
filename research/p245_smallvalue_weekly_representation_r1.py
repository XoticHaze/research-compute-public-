import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['AVUV','AVDV','IJR','VSS','SPY']; W={'2020':'2020-01-01','2021':'2021-01-01','2022':'2022-01-01'}; B=10; BLOCK=13; N=5000; RNG=np.random.default_rng(245)
def cagr(r):
 q=np.asarray(r,float); return float(np.prod(1+q)**(52/len(q))-1)
def cost(r):
 q=np.asarray(r,float).copy(); f=B/10000
 if len(q): q[0]-=f; q[-1]-=f
 return q
def boot(a,b):
 n=len(a); vals=[]
 for _ in range(N):
  idx=[]
  while len(idx)<n:
   s=int(RNG.integers(0,max(n-BLOCK+1,1))); idx.extend(range(s,min(s+BLOCK,n)))
  j=np.array(idx[:n]); vals.append(cagr(cost(a[j]))-cagr(cost(b[j])))
 v=np.asarray(vals); return {'p_nonpositive':float(np.mean(v<=0)),'median':float(np.median(v)),'p05':float(np.quantile(v,.05)),'p95':float(np.quantile(v,.95))}
r0=yf.download(A,start='2019-10-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=r0['Close'][A] if isinstance(r0.columns,pd.MultiIndex) else r0[A]; r=cl.dropna(how='any').resample('W-FRI').last().pct_change().dropna(how='any'); tests={}
for k,s in W.items():
 d=r.loc[pd.Timestamp(s):]; cand=.5*d.AVUV.to_numpy()+.5*d.AVDV.to_numpy(); ctrl=.5*d.IJR.to_numpy()+.5*d.VSS.to_numpy(); spy=d.SPY.to_numpy(); tests[k]={'rows':len(d),'actual_vs_matched':cagr(cost(cand))-cagr(cost(ctrl)),'actual_vs_spy':cagr(cost(cand))-cagr(cost(spy)),'matched_bootstrap':boot(cand,ctrl)}
ok=all(tests[k]['actual_vs_matched']>0 and tests[k]['matched_bootstrap']['p_nonpositive']<=.10 for k in W)
out={'schema':'research.p245_smallvalue_weekly_representation_r1','parent':'P239/P240/P241/P242/P243','claim':'fixed AVUV/AVDV matched excess survives an alternate weekly representation with serial-dependence-preserving resampling','contract':{'frequency':'weekly Friday close','candidate_weights':{'AVUV':0.5,'AVDV':0.5},'matched_control_weights':{'IJR':0.5,'VSS':0.5},'windows':W,'cost_bps':B,'block_weeks':BLOCK,'samples':N,'seed':245,'no_weight_window_fund_or_parameter_search':True},'tests':tests,'decision':'P245_SUPPORT' if ok else 'P245_REPRESENTATION_NOT_SUPPORTED','limitations':['same Yahoo adjusted-price source as prior monthly tests','weekly endpoint remains a sampled representation'],'boundaries':{'portfolio_ranking':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p245_smallvalue_weekly_representation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True)); print(json.dumps(out,sort_keys=True))
