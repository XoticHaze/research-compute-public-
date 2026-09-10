import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['XMMO','IJH','SPY']; W={'2006':'2006-01-01','2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; B=10

def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}

def cost(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q

def ev(d):
 m={a:met(cost(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:met(cost(q[a])) for a in A}; fs.append({'fold':i,'xmmo_minus_ijh':mm['XMMO']['cagr']-mm['IJH']['cagr'],'xmmo_minus_spy':mm['XMMO']['cagr']-mm['SPY']['cagr']})
 return {'metrics':m,'xmmo_minus_ijh':m['XMMO']['cagr']-m['IJH']['cagr'],'xmmo_minus_spy':m['XMMO']['cagr']-m['SPY']['cagr'],'positive_ijh_folds':sum(x['xmmo_minus_ijh']>0 for x in fs),'positive_spy_folds':sum(x['xmmo_minus_spy']>0 for x in fs),'folds':fs}
raw=yf.download(A,start='2005-01-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; a,b,c,d=(tests[k] for k in ['2006','2010','2015','2020']); decision='P217_MIDCAP_MOMENTUM_SURVIVOR' if all(x['xmmo_minus_ijh']>0 and x['xmmo_minus_spy']>0 for x in (a,b,c,d)) and b['positive_ijh_folds']>=4 and b['positive_spy_folds']>=4 else 'P217_MIDCAP_MOMENTUM_REJECT'; out={'schema':'research.p217_midcap_momentum_r1','parent':'P217','hypothesis':'Mid-cap momentum ETF XMMO transports momentum into durable after-cost excess versus size-matched IJH and SPY.','contract':{'candidate':'XMMO','matched_control':'IJH','opportunity_cost':'SPY','windows':W,'chronological_folds':5,'external_cost_bps_entry_exit':B,'gate':'positive XMMO-IJH and XMMO-SPY CAGR every window; >=4/5 positive 2010 folds versus each','no_window_weight_timing_or_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':decision,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p217_midcap_momentum_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
