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
 ex=float(q['exp'].mean()); matched=q['spy']*ex; out={'days':len(q),'avg_exposure':ex,'controls':{'exposure_matched_spy':mt(matched),'full_spy':mt(q['spy'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q['gross']-q['turn']*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a['gross']-a['turn']*bp/10000; z=a['spy']*ex; fs.append({'fold':j,'matched':cg(x)-cg(z),'spy':cg(x)-cg(a['spy'])})
  out['costs'][str(bp)]={'candidate':m,'excess_matched':m['cagr']-out['controls']['exposure_matched_spy']['cagr'],'excess_spy':m['cagr']-out['controls']['full_spy']['cagr'],'positive_matched_folds':sum(x['matched']>0 for x in fs),'positive_spy_folds':sum(x['spy']>0 for x in fs),'folds':fs}
 return out
def main():
 p=yf.download('SPY',start='1993-01-01',auto_adjust=True,progress=False,threads=False)['Close']; p=p.iloc[:,0] if isinstance(p,pd.DataFrame) else p; p=p.dropna().astype(float); r=p.pct_change(fill_method=None); idx=p.index; g=pd.Series(np.arange(len(idx)),index=idx); month=pd.Series(idx.to_period('M'),index=idx); first3=g.groupby(month).rank(method='first')<=3; last=g.groupby(month).rank(method='first',ascending=False)==1; exp=(first3|last).astype(float); q=pd.DataFrame({'gross':exp*r,'turn':exp.diff().abs().fillna(exp),'spy':r,'exp':exp}).dropna(); tests={k:ev(q.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['5']; b=tests['2020']['costs']['5']; ok=a['excess_matched']>0 and b['excess_matched']>0 and a['positive_matched_folds']>=3 and b['positive_matched_folds']>=3
 out={'schema':'research.p121_turn_month_spy_r1','parent':'P121','hypothesis':'A fixed SPY turn-of-month window, last trading day plus first three trading days of each month, creates persistent after-cost excess beyond identical average capital usage.','contract':{'asset':'SPY','signal':'long last trading day of month and first three trading days of next/current month; calendar-known ex ante','cost_bps_per_position_change':list(COSTS),'matched_control':'continuous SPY scaled to candidate average exposure','opportunity_control':'full SPY','windows':['2010','2015','2020'],'folds':5,'window_search':False},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_date':str(p.index[-1].date()),'series_sha256':hashlib.sha256(p.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P121_TURN_MONTH_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P121_TURN_MONTH_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p121_turn_month_spy_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
