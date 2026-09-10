import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['EFV','EFA','SPY']; W={'2006':'2006-01-01','2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; B=10
def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def cost(r):
 q=pd.Series(r).dropna().copy(); f=B/10000
 if len(q): q.iloc[0]=(1+q.iloc[0])*(1-f)-1; q.iloc[-1]=(1+q.iloc[-1])*(1-f)-1
 return q
def ev(d):
 m={a:met(cost(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:met(cost(q[a])) for a in A}; fs.append({'fold':i,'efv_minus_efa':mm['EFV']['cagr']-mm['EFA']['cagr'],'efv_minus_spy':mm['EFV']['cagr']-mm['SPY']['cagr']})
 return {'metrics':m,'efv_minus_efa':m['EFV']['cagr']-m['EFA']['cagr'],'efv_minus_spy':m['EFV']['cagr']-m['SPY']['cagr'],'positive_efa_folds':sum(x['efv_minus_efa']>0 for x in fs),'folds':fs}
raw=yf.download(A,start='2005-01-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any'); r=cl.resample('ME').last().pct_change().dropna(how='any'); t={k:ev(r.loc[pd.Timestamp(v):]) for k,v in W.items()}; a,b,c=t['2010'],t['2015'],t['2020']; dec='P209_DEVELOPED_VALUE_SURVIVOR' if all(x['efv_minus_efa']>0 for x in (a,b,c)) and a['positive_efa_folds']>=4 and a['efv_minus_spy']>=0 else 'P209_DEVELOPED_VALUE_REJECT'; out={'schema':'research.p209_developed_value_fund_r1','parent':'P209','hypothesis':'Developed-market value (EFV) creates durable excess over its geography-matched EFA baseline and clears US-equity opportunity cost.','contract':{'candidate':'EFV','matched':'EFA','opportunity_cost':'SPY','windows':W,'folds':5,'external_cost_bps_one_way':B,'gate':'positive EFV-EFA CAGR in 2010+,2015+,2020+; >=4/5 positive 2010 folds; nonnegative 2010 EFV-SPY','no_parameter_window_weight_or_control_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':t,'decision':dec,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p209_developed_value_fund_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))