import hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['SYLD','VTV','SPY']; W={'2014':'2014-01-01','2016':'2016-01-01','2020':'2020-01-01'}; B=10

def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}

def cost(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]-=f; q.iloc[-1]-=f
 return q

def ev(d):
 m={a:met(cost(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:met(cost(q[a])) for a in A}; fs.append({'fold':i,'syld_minus_vtv':mm['SYLD']['cagr']-mm['VTV']['cagr'],'syld_minus_spy':mm['SYLD']['cagr']-mm['SPY']['cagr']})
 return {'metrics':m,'syld_minus_vtv':m['SYLD']['cagr']-m['VTV']['cagr'],'syld_minus_spy':m['SYLD']['cagr']-m['SPY']['cagr'],'positive_vtv_folds':sum(x['syld_minus_vtv']>0 for x in fs),'positive_spy_folds':sum(x['syld_minus_spy']>0 for x in fs),'folds':fs}
raw=yf.download(A,start='2013-01-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any').resample('ME').last(); r=cl.pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; a,b,c=(tests[k] for k in ['2014','2016','2020']); decision='P215_SHAREHOLDER_YIELD_SURVIVOR' if all(x['syld_minus_vtv']>0 and x['syld_minus_spy']>0 for x in (a,b,c)) and a['positive_vtv_folds']>=4 and a['positive_spy_folds']>=4 else 'P215_SHAREHOLDER_YIELD_REJECT'; out={'schema':'research.p215_shareholder_yield_r1','parent':'P215','hypothesis':'A shareholder-yield equity fund (SYLD), combining repurchases/dividends/debt reduction with fundamental selection, creates durable after-cost excess over style-matched VTV and SPY.','contract':{'candidate':'SYLD','matched_control':'VTV','opportunity_cost':'SPY','windows':W,'chronological_folds':5,'external_cost_bps_entry_exit':B,'gate':'positive SYLD-VTV and SYLD-SPY CAGR every window; >=4/5 positive 2014 folds versus each','no_window_weight_timing_or_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':decision,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p215_shareholder_yield_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))
