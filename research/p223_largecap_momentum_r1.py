import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['MTUM','IVV','SPY']; W={'2014':'2014-01-01','2015':'2015-01-01','2020':'2020-01-01'}; B=10

def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def cost(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q
def ev(d):
 m={a:met(cost(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:met(cost(q[a])) for a in A}; fs.append({'fold':i,'mtum_minus_ivv':mm['MTUM']['cagr']-mm['IVV']['cagr'],'mtum_minus_spy':mm['MTUM']['cagr']-mm['SPY']['cagr']})
 return {'metrics':m,'mtum_minus_ivv':m['MTUM']['cagr']-m['IVV']['cagr'],'mtum_minus_spy':m['MTUM']['cagr']-m['SPY']['cagr'],'positive_ivv_folds':sum(x['mtum_minus_ivv']>0 for x in fs),'folds':fs}
raw=yf.download(A,start='2013-04-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; gate=all(tests[k]['mtum_minus_ivv']>0 for k in W) and tests['2015']['positive_ivv_folds']>=4 and tests['2015']['mtum_minus_spy']>0; decision='P223_LARGECAP_MOMENTUM_SUPPORT' if gate else 'P223_LARGECAP_MOMENTUM_NOT_SUPPORTED'; out={'schema':'research.p223_largecap_momentum_r1','parent':'P223','hypothesis':'A fixed large-cap momentum fund (MTUM) creates durable after-cost excess versus a matched large-cap index (IVV) and SPY, testing whether the P217/P219 seam transports beyond mid-caps.','contract':{'candidate':'MTUM','primary_matched_control':'IVV','opportunity_context':'SPY','windows':W,'chronological_folds':5,'external_cost_bps_entry_exit':B,'gate':'positive MTUM-IVV every window, >=4/5 positive IVV folds from 2015, and positive MTUM-SPY from 2015','no_window_fund_or_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':decision,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p223_largecap_momentum_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))