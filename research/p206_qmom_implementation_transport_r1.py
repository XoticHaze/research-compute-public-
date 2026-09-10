import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['QMOM','MTUM','SPY','IWF']; WINDOWS={'2016':'2016-01-01','2019':'2019-01-01','2020':'2020-01-01'}; BPS=10
def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def cost(r):
 q=pd.Series(r).dropna().copy(); f=BPS/10000
 if len(q): q.iloc[0]=(1+q.iloc[0])*(1-f)-1; q.iloc[-1]=(1+q.iloc[-1])*(1-f)-1
 return q
def ev(d):
 m={a:met(cost(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:met(cost(q[a])) for a in A}; fs.append({'fold':i,'qmom_minus_mtum':mm['QMOM']['cagr']-mm['MTUM']['cagr'],'qmom_minus_iwf':mm['QMOM']['cagr']-mm['IWF']['cagr'],'qmom_minus_spy':mm['QMOM']['cagr']-mm['SPY']['cagr']})
 return {'months':len(d),'metrics':m,'qmom_minus_mtum':m['QMOM']['cagr']-m['MTUM']['cagr'],'qmom_minus_iwf':m['QMOM']['cagr']-m['IWF']['cagr'],'qmom_minus_spy':m['QMOM']['cagr']-m['SPY']['cagr'],'positive_mtum_folds':sum(x['qmom_minus_mtum']>0 for x in fs),'positive_iwf_folds':sum(x['qmom_minus_iwf']>0 for x in fs),'folds':fs}
raw=yf.download(A,start='2015-12-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any'); r=cl.resample('ME').last().pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(v):]) for k,v in WINDOWS.items()}; p,p19,p20=tests['2016'],tests['2019'],tests['2020']; dec='P206_QMOM_IMPLEMENTATION_SURVIVOR' if all(x['qmom_minus_mtum']>0 and x['qmom_minus_iwf']>0 for x in (p,p19,p20)) and p['positive_mtum_folds']>=3 and p['positive_iwf_folds']>=3 and p['metrics']['QMOM']['maxdd']>=p['metrics']['MTUM']['maxdd'] else 'P206_QMOM_IMPLEMENTATION_REJECT'; out={'schema':'research.p206_qmom_implementation_transport_r1','parent':'P206','hypothesis':'A more concentrated momentum implementation (QMOM) transports the independently observed momentum premium better than MTUM and clears growth-style opportunity cost.','contract':{'candidate':'QMOM','controls':['MTUM','IWF','SPY'],'windows':WINDOWS,'folds':5,'external_cost_bps_one_way':BPS,'gate':'positive excess versus MTUM and IWF in all frozen windows; >=3/5 positive folds versus each; max drawdown no worse than MTUM','no_parameter_window_weight_or_control_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':dec,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p206_qmom_implementation_transport_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))