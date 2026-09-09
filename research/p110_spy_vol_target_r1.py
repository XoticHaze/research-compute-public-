from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
VOL_WIN=20; TARGET=.10; CAP=1.0; COSTS=(1,5,10)

def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(252/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(252)); a=float(r.mean()*252); return {'cagr':cg(r),'sharpe_rf0':a/v if v else None,'maxdd':float((e/e.cummax()-1).min()),'annual_vol':v}
def ev(q):
 exposure=float(q['exp'].mean()); static=q['spy']*exposure; out={'days':len(q),'avg_exposure':exposure,'controls':{'exposure_matched_static_spy':mt(static),'full_spy':mt(q['spy'])},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q['gross']-q['turn']*bp/10000; m=mt(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a['gross']-a['turn']*bp/10000; s=a['spy']*exposure; fs.append({'fold':j,'matched':cg(x)-cg(s),'spy':cg(x)-cg(a['spy'])})
  out['costs'][str(bp)]={'candidate':m,'excess_matched':m['cagr']-out['controls']['exposure_matched_static_spy']['cagr'],'excess_spy':m['cagr']-out['controls']['full_spy']['cagr'],'sharpe_delta_matched':m['sharpe_rf0']-out['controls']['exposure_matched_static_spy']['sharpe_rf0'],'dd_delta_spy':m['maxdd']-out['controls']['full_spy']['maxdd'],'positive_matched_folds':sum(x['matched']>0 for x in fs),'positive_spy_folds':sum(x['spy']>0 for x in fs),'folds':fs}
 return out
def main():
 p=yf.download('SPY',start='2000-01-01',auto_adjust=True,progress=False,threads=False)['Close']; p=p.iloc[:,0] if isinstance(p,pd.DataFrame) else p; p=p.dropna().astype(float); r=p.pct_change(fill_method=None); rv=r.rolling(VOL_WIN).std(ddof=1)*math.sqrt(252); # exposure for t return uses realized vol known through t-1
 exp=(TARGET/rv.shift(1)).clip(lower=0,upper=CAP); prev=exp.shift(1).fillna(0); q=pd.DataFrame({'gross':exp*r,'turn':(exp-prev).abs(),'spy':r,'exp':exp}).dropna(); tests={k:ev(q.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['5']; b=tests['2020']['costs']['5']; ok=a['excess_matched']>0 and b['excess_matched']>0 and a['positive_matched_folds']>=3 and b['positive_matched_folds']>=3 and b['sharpe_delta_matched']>0
 out={'schema':'research.p110_spy_vol_target_r1','parent':'P110','hypothesis':'A fixed causal 10% volatility target on SPY creates after-cost risk-timing value beyond static SPY at identical average capital usage.','contract':{'asset':'SPY','realized_vol_window_days':VOL_WIN,'target_annual_vol':TARGET,'max_exposure':CAP,'signal_lag':'exposure for day t uses realized volatility known through t-1','cost_bps_per_exposure_change':list(COSTS),'matched_control':'continuous SPY scaled to candidate average exposure','opportunity_control':'full SPY','windows':['2010','2015','2020'],'folds':5,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_date':str(p.index[-1].date()),'series_sha256':hashlib.sha256(p.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P110_SPY_VOL_TARGET_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P110_SPY_VOL_TARGET_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p110_spy_vol_target_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
