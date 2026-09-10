import hashlib,json,math
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
A=['VBR','IWM','IWD','SPY']; WINDOWS={'2005':'2005-01-01','2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}; BPS=10
def met(r):
 r=pd.Series(r).dropna(); e=(1+r).cumprod(); n=len(r); c=float(e.iloc[-1]**(12/n)-1); v=float(r.std(ddof=0)*12**.5); return {'cagr':c,'sharpe':float(r.mean()*12/v) if v else None,'maxdd':float((e/e.cummax()-1).min())}
def cost(r):
 q=pd.Series(r).dropna().copy(); f=BPS/10000
 if len(q): q.iloc[0]=(1+q.iloc[0])*(1-f)-1; q.iloc[-1]=(1+q.iloc[-1])*(1-f)-1
 return q
def ev(d):
 m={a:met(cost(d[a])) for a in A}; fs=[]
 for i,ix in enumerate(np.array_split(np.arange(len(d)),5),1):
  q=d.iloc[ix]; mm={a:met(cost(q[a])) for a in A}; fs.append({'fold':i,'vbr_minus_iwm':mm['VBR']['cagr']-mm['IWM']['cagr'],'vbr_minus_iwd':mm['VBR']['cagr']-mm['IWD']['cagr'],'vbr_minus_spy':mm['VBR']['cagr']-mm['SPY']['cagr']})
 return {'months':len(d),'metrics':m,'vbr_minus_iwm':m['VBR']['cagr']-m['IWM']['cagr'],'vbr_minus_iwd':m['VBR']['cagr']-m['IWD']['cagr'],'vbr_minus_spy':m['VBR']['cagr']-m['SPY']['cagr'],'positive_iwm_folds':sum(x['vbr_minus_iwm']>0 for x in fs),'positive_iwd_folds':sum(x['vbr_minus_iwd']>0 for x in fs),'folds':fs}
raw=yf.download(A,start='2004-01-30',end='2026-09-03',auto_adjust=True,progress=False,group_by='column',threads=False); cl=raw['Close'][A] if isinstance(raw.columns,pd.MultiIndex) else raw[A]; cl=cl.dropna(how='any'); r=cl.resample('ME').last().pct_change().dropna(how='any'); tests={k:ev(r.loc[pd.Timestamp(v):]) for k,v in WINDOWS.items()}; p10,p15,p20=tests['2010'],tests['2015'],tests['2020']; dec='P207_SMALLVALUE_INTERSECTION_SURVIVOR' if all(x['vbr_minus_iwm']>0 and x['vbr_minus_iwd']>0 for x in (p10,p15,p20)) and p10['positive_iwm_folds']>=4 and p10['positive_iwd_folds']>=4 and p10['vbr_minus_spy']>0 else 'P207_SMALLVALUE_INTERSECTION_REJECT'; out={'schema':'research.p207_smallvalue_intersection_fund_r1','parent':'P207','hypothesis':'The investable small-cap/value intersection (VBR) creates persistent excess beyond either small-cap beta (IWM) or value beta (IWD), rather than merely repackaging one axis.','contract':{'candidate':'VBR','matched_controls':{'small_cap':'IWM','value':'IWD'},'opportunity_cost':'SPY','windows':WINDOWS,'folds':5,'external_cost_bps_one_way':BPS,'gate':'2010+, 2015+, 2020+ positive excess versus IWM and IWD; >=4/5 positive 2010 folds versus each; 2010+ positive excess versus SPY','no_asset_window_weight_cost_or_control_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','rows':len(cl),'first':str(cl.index[0]),'last':str(cl.index[-1]),'panel_sha256':hashlib.sha256(cl.to_csv().encode()).hexdigest()},'tests':tests,'decision':dec,'boundaries':{'portfolio_ranking':False,'product_runtime':False,'broker':False,'live_trading':False}}
Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p207_smallvalue_intersection_fund_r1.json').write_text(json.dumps(out,sort_keys=True,indent=2)); print(json.dumps(out,sort_keys=True))