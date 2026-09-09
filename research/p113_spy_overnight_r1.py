from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(1,2,5)
def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(252/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(252)); a=float(r.mean()*252); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def ev(q):
 out={'days':len(q),'controls':{'full_close_to_close_spy':mt(q['cc']),'intraday_open_to_close':mt(q['intra'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q['overnight']-2*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a['overnight']-2*bp/10000; fs.append({'fold':j,'spy':cg(x)-cg(a['cc']),'intraday':cg(x)-cg(a['intra'])})
  out['costs'][str(bp)]={'candidate':m,'excess_spy':m['cagr']-out['controls']['full_close_to_close_spy']['cagr'],'excess_intraday':m['cagr']-out['controls']['intraday_open_to_close']['cagr'],'positive_spy_folds':sum(x['spy']>0 for x in fs),'positive_intraday_folds':sum(x['intraday']>0 for x in fs),'folds':fs}
 return out
def main():
 x=yf.download('SPY',start='2000-01-01',auto_adjust=True,progress=False,threads=False); o=x['Open']; c=x['Close']; o=o.iloc[:,0] if isinstance(o,pd.DataFrame) else o; c=c.iloc[:,0] if isinstance(c,pd.DataFrame) else c; q=pd.DataFrame({'overnight':o/c.shift(1)-1,'intra':c/o-1,'cc':c/c.shift(1)-1}).dropna(); tests={k:ev(q.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['2']; b=tests['2020']['costs']['2']; ok=a['excess_spy']>0 and b['excess_spy']>0 and a['positive_spy_folds']>=3 and b['positive_spy_folds']>=3
 out={'schema':'research.p113_spy_overnight_r1','parent':'P113','hypothesis':'SPY close-to-next-open overnight returns remain an investable after-cost return source after explicit daily round-trip friction.','contract':{'asset':'SPY','return':'adjusted close t-1 to adjusted open t','cost_bps_each_side':list(COSTS),'daily_round_trip_cost':'2x stated bps','matched_opportunity_control':'full close-to-close SPY','orthogonal_attribution_control':'open-to-close SPY','windows':['2010','2015','2020'],'folds':5,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only adjusted OHLC','last_date':str(q.index[-1].date()),'panel_sha256':hashlib.sha256(q.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P113_SPY_OVERNIGHT_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P113_SPY_OVERNIGHT_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p113_spy_overnight_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
