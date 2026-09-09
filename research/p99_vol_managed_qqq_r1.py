import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
C=(1,5,10); TARGET=.15; LOOKBACK=20; CAP=1.5

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(252/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(252)); ann=float(r.mean()*252); return {'cagr':cagr(r),'sharpe':ann/vol if vol else None,'maxdd':float((e/e.cummax()-1).min()),'vol':vol}
def main():
 q=yf.download(['QQQ'],start='2000-01-01',auto_adjust=True,progress=False,threads=False); c=q['Close']['QQQ'].astype(float).dropna(); r=c.pct_change(); rv=r.rolling(LOOKBACK).std(ddof=1)*math.sqrt(252); exp=(TARGET/rv).clip(lower=0,upper=CAP).shift(1); f=pd.DataFrame({'qqq':r,'exposure':exp}).dropna(); f['gross']=f.exposure*f.qqq; f['turnover']=f.exposure.diff().abs().fillna(f.exposure.abs())
 out={'schema':'research.p99_vol_managed_qqq_r1','parent':'P99','hypothesis':'A causal fixed-target volatility-managed QQQ exposure can create durable after-cost excess and better risk efficiency versus static 1x QQQ without binary timing or parameter search.','contract':{'realized_vol_lookback_days':LOOKBACK,'annual_target_vol':TARGET,'max_exposure':CAP,'exposure_lag_days':1,'cost_bps_per_unit_exposure_change':list(C),'matched_and_opportunity_control':'static 1x QQQ same dates','windows':['full','2015','2020'],'folds':5,'no_parameter_search':True},'tests':{}}
 for name,start in [('full',None),('2015','2015-01-01'),('2020','2020-01-01')]:
  x=f if start is None else f.loc[start:]; base=mt(x.qqq); d={'days':len(x),'avg_exposure':float(x.exposure.mean()),'median_exposure':float(x.exposure.median()),'fraction_levered':float((x.exposure>1).mean()),'control':base,'costs':{}}; ids=np.array_split(np.arange(len(x)),5)
  for bp in C:
   net=x.gross-x.turnover*bp/10000; cm=mt(net); folds=[]
   for j,ix in enumerate(ids,1):
    a=x.iloc[ix]; cand=a.gross-a.turnover*bp/10000; folds.append({'fold':j,'excess_cagr_vs_qqq':cagr(cand)-cagr(a.qqq)})
   d['costs'][str(bp)]={'candidate':cm,'excess_cagr_vs_qqq':cm['cagr']-base['cagr'],'sharpe_delta_vs_qqq':cm['sharpe']-base['sharpe'],'maxdd_delta_vs_qqq':cm['maxdd']-base['maxdd'],'positive_excess_folds':sum(z['excess_cagr_vs_qqq']>0 for z in folds),'folds':folds,'annualized_turnover':float(x.turnover.mean()*252)}
  out['tests'][name]=d
 a=out['tests']['2015']['costs']['5']; b=out['tests']['2020']['costs']['5']; out['decision']='P99_VOL_MANAGED_QQQ_SUPPORTED' if a['excess_cagr_vs_qqq']>0 and b['excess_cagr_vs_qqq']>0 and b['positive_excess_folds']>=3 and b['sharpe_delta_vs_qqq']>0 else 'P99_VOL_MANAGED_QQQ_NOT_SUPPORTED'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p99_vol_managed_qqq_r1.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out))
if __name__=='__main__': main()
