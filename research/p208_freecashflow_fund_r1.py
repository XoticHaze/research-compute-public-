import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['COWZ','IWD','SPY']; WINDOWS={'2018':'2018-01-01','2020':'2020-01-01','2022':'2022-01-01'}; BPS=10
def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def cost(r):
 q=pd.Series(r).dropna().copy(); f=BPS/10000
 if len(q): q.iloc[0]=(1+q.iloc[0])*(1-f)-1; q.iloc[-1]=(1+q.iloc[-1])*(1-f)-1
 return q
def ev(d):
 m={a:met(cost(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:met(cost(q[a])) for a in A}; fs.append({'fold':i,'cowz_minus_iwd':mm['COWZ']['cagr']-mm['IWD']['cagr'],'cowz_minus_spy':mm['COWZ']['cagr']-mm['SPY']['cagr']})
 return {'months':len(d),'metrics':m,'cowz_minus_iwd':m['COWZ']['cagr']-m['IWD']['cagr'],'cowz_minus_spy':m['COWZ']['cagr']-m['SPY']['cagr'],'positive_iwd_folds':sum(x['cowz_minus_iwd']>0 for x in fs),'positive_spy_folds':sum(x['cowz_minus_spy']>0 for x in fs),'folds':fs}
raw=yf.download(A,start='2017-01-01',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any'); r=cl.resample('ME').last().pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(v):]) for k,v in WINDOWS.items()}; p,p20,p22=tests['2018'],tests['2020'],tests['2022']; dec='P208_FREECASHFLOW_FUND_SURVIVOR' if all(x['cowz_minus_iwd']>0 and x['cowz_minus_spy']>0 for x in (p,p20,p22)) and p['positive_iwd_folds']>=3 and p['positive_spy_folds']>=3 and p['metrics']['COWZ']['maxdd']>=p['metrics']['SPY']['maxdd'] else 'P208_FREECASHFLOW_FUND_REJECT'; out={'schema':'research.p208_freecashflow_fund_r1','parent':'P208','hypothesis':'A free-cash-flow-yield fund implementation (COWZ) creates persistent incremental excess beyond conventional value (IWD) and broad US equity (SPY).','contract':{'candidate':'COWZ','matched_control':'IWD','opportunity_cost':'SPY','windows':WINDOWS,'folds':5,'external_cost_bps_one_way':BPS,'gate':'positive CAGR excess versus IWD and SPY in 2018+, 2020+, 2022+; >=3/5 positive full-sample folds versus each; max drawdown no worse than SPY','no_parameter_window_weight_cost_or_control_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':dec,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p208_freecashflow_fund_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))