from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(1,5,10)
def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(252/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(252)); a=float(r.mean()*252); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q):
 out={'days':len(q),'controls':{'full_spy':mt(q['spy']),'intraday_complement':mt(q['intraday'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q['overnight']-2*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a['overnight']-2*bp/10000; fs.append({'fold':j,'spy':cg(x)-cg(a['spy'])})
  out['costs'][str(bp)]={'candidate':m,'excess_spy':m['cagr']-out['controls']['full_spy']['cagr'],'positive_spy_folds':sum(x['spy']>0 for x in fs),'folds':fs}
 return out
def main():
 d=yf.download('SPY',start='1993-01-01',auto_adjust=True,progress=False,threads=False); o=d['Open']; c=d['Close']; o=o.iloc[:,0] if isinstance(o,pd.DataFrame) else o; c=c.iloc[:,0] if isinstance(c,pd.DataFrame) else c; x=pd.DataFrame({'open':o,'close':c}).dropna().astype(float); overnight=x['open']/x['close'].shift(1)-1; intraday=x['close']/x['open']-1; spy=x['close']/x['close'].shift(1)-1; q=pd.DataFrame({'overnight':overnight,'intraday':intraday,'spy':spy}).dropna(); tests={k:ev(q.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['1']; b=tests['2020']['costs']['1']; ok=a['excess_spy']>0 and b['excess_spy']>0 and a['positive_spy_folds']>=3 and b['positive_spy_folds']>=3
 out={'schema':'research.p125_spy_overnight_r1','parent':'P125','hypothesis':'The SPY close-to-next-open overnight component retains durable after-cost return exceeding full close-to-close SPY despite a daily round trip.','contract':{'asset':'SPY','holding':'close t-1 to open t every trading day','roundtrip_cost_bps_per_side':list(COSTS),'matched_control':'full SPY close-to-close, same capital committed each overnight','diagnostic_control':'open-to-close intraday complement','windows':['2010','2015','2020'],'folds':5,'parameter_search':False},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_date':str(x.index[-1].date()),'ohlc_sha256':hashlib.sha256(x.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P125_SPY_OVERNIGHT_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P125_SPY_OVERNIGHT_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p125_spy_overnight_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
