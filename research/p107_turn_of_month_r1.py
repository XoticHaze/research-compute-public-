from __future__ import annotations
import json,math,hashlib
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
COSTS=(1,5,10)

def met(r,ann=252):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(ann)); a=float(r.mean()*ann); c=float((1+r).prod()**(ann/len(r))-1); return {'cagr':c,'sharpe_rf0':a/vol if vol else None,'maxdd':float((e/e.cummax()-1).min()),'annual_vol':vol}
def ev(q):
 exposure=float(q.exposure.mean()); scaled=q.spy*exposure; z={'days':len(q),'capital_usage':exposure,'controls':{'exposure_matched_static_spy':met(scaled),'full_spy':met(q.spy)},'costs':{}}; ids=np.array_split(np.arange(len(q)),5)
 for bp in COSTS:
  n=q.gross-q.turn*bp/10000; m=met(n); fs=[]
  for j,ix in enumerate(ids,1):
   a=q.iloc[ix]; x=a.gross-a.turn*bp/10000; sx=a.spy*exposure; fs.append({'fold':j,'exposure_matched':met(x)['cagr']-met(sx)['cagr'],'full_spy':met(x)['cagr']-met(a.spy)['cagr']})
  z['costs'][str(bp)]={'candidate':m,'excess_exposure_matched':m['cagr']-z['controls']['exposure_matched_static_spy']['cagr'],'excess_full_spy':m['cagr']-z['controls']['full_spy']['cagr'],'sharpe_delta_exposure_matched':m['sharpe_rf0']-z['controls']['exposure_matched_static_spy']['sharpe_rf0'],'dd_delta_full_spy':m['maxdd']-z['controls']['full_spy']['maxdd'],'positive_exposure_matched_folds':sum(x['exposure_matched']>0 for x in fs),'positive_full_spy_folds':sum(x['full_spy']>0 for x in fs),'folds':fs}
 return z
def main():
 p=yf.download('SPY',start='2000-01-01',auto_adjust=True,progress=False,threads=False)['Close']; p=p.iloc[:,0] if isinstance(p,pd.DataFrame) else p; p=p.dropna().astype(float); idx=p.index; pos=pd.Series(0.0,index=idx); g=pd.Series(idx.to_period('M'),index=idx)
 for _,dates in pd.Series(idx,index=idx).groupby(g):
  ds=list(dates.values); chosen=set(ds[:3]+ds[-1:]); pos.loc[[d for d in idx if d.to_datetime64() in chosen]]=1.0
 # return from close t to close t+1 is positioned using the known calendar classification of t+1
 ret=p.pct_change(); exp=pos; prev=exp.shift(1).fillna(0); turn=(exp-prev).abs(); q=pd.DataFrame({'gross':exp*ret,'turn':turn,'spy':ret,'exposure':exp}).dropna(); tests={k:ev(q.loc[v:]) for k,v in {'2010':'2010-01-01','2015':'2015-01-01','2020':'2020-01-01'}.items()}; a=tests['2015']['costs']['5']; b=tests['2020']['costs']['5']; ok=a['excess_exposure_matched']>0 and b['excess_exposure_matched']>0 and a['positive_exposure_matched_folds']>=3 and b['positive_exposure_matched_folds']>=3 and b['sharpe_delta_exposure_matched']>0
 out={'schema':'research.p107_turn_of_month_r1','parent':'P107','hypothesis':'A fixed turn-of-month SPY calendar window creates after-cost timing alpha per unit capital beyond exposure-matched static SPY, while full-SPY opportunity cost is measured separately.','contract':{'window':'first 3 trading days plus last trading day of each month','execution':'position for a return day determined by known exchange-calendar day classification','cost_bps_per_position_change':list(COSTS),'matched_control':'continuous SPY exposure scaled to candidate average capital usage','opportunity_control':'full SPY','windows':['2010','2015','2020'],'folds':5,'no_parameter_search':True},'source':{'provider':'Yahoo Finance via yfinance; research-only','last_date':str(p.index[-1].date()),'series_sha256':hashlib.sha256(p.reset_index().to_csv(index=False).encode()).hexdigest()},'tests':tests,'decision':'P107_TURN_OF_MONTH_SUPPORTED_FOR_FURTHER_FALSIFICATION' if ok else 'P107_TURN_OF_MONTH_NOT_SUPPORTED'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p107_turn_of_month_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True,allow_nan=False))
if __name__=='__main__': main()
