import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
C=(1,5,10)
def cg(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(252/len(r))-1)
def mt(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); v=float(r.std(ddof=1)*math.sqrt(252)); a=float(r.mean()*252); return {'cagr':cg(r),'sharpe':a/v if v else None,'maxdd':float((e/e.cummax()-1).min())}
def main():
 q=yf.download(['QQQ'],start='2000-01-01',auto_adjust=True,progress=False,threads=False); o=q['Open']['QQQ'].astype(float); c=q['Close']['QQQ'].astype(float); f=pd.DataFrame({'open':o,'close':c}).dropna(); f['prev_close']=f.close.shift(1); f['overnight_gap']=f.open/f.prev_close-1; f['intraday']=f.close/f.open-1; f['cc']=f.close/f.prev_close-1; f=f.dropna(); f['active']=f.overnight_gap<0; f['gross']=np.where(f.active,f.intraday,0.0); f['always_intraday']=f.intraday
 out={'schema':'research.p96_overnight_gap_reversal_r1','parent':'P96','hypothesis':'A negative QQQ overnight gap predicts same-day intraday reversal strongly enough to improve on always holding QQQ open-to-close after realistic round-trip costs.','contract':{'signal':'known at open: QQQ open/previous close < 0','return':'same-day open-to-close when active, cash otherwise','costs_bps_roundtrip':list(C),'matched_control':'always hold every QQQ open-to-close','opportunity_control':'QQQ previous-close-to-close','windows':['full','2015','2020'],'folds':5,'no_parameter_search':True},'tests':{}}
 for name,start in [('full',None),('2015','2015-01-01'),('2020','2020-01-01')]:
  x=f if start is None else f.loc[start:]; d={'days':len(x),'active_fraction':float(x.active.mean()),'controls':{'always_intraday':mt(x.always_intraday),'qqq_close_close':mt(x.cc)},'costs':{}}; ids=np.array_split(np.arange(len(x)),5)
  for bp in C:
   net=x.gross-x.active.astype(float)*bp/10000; cm=mt(net); folds=[]
   for j,ix in enumerate(ids,1):
    a=x.iloc[ix]; cand=a.gross-a.active.astype(float)*bp/10000; folds.append({'fold':j,'excess_cagr_vs_always_intraday':cg(cand)-cg(a.always_intraday),'excess_cagr_vs_qqq':cg(cand)-cg(a.cc)})
   d['costs'][str(bp)]={'candidate':cm,'excess_cagr_vs_always_intraday':cm['cagr']-d['controls']['always_intraday']['cagr'],'excess_cagr_vs_qqq':cm['cagr']-d['controls']['qqq_close_close']['cagr'],'sharpe_delta_vs_always_intraday':cm['sharpe']-d['controls']['always_intraday']['sharpe'],'maxdd_delta_vs_always_intraday':cm['maxdd']-d['controls']['always_intraday']['maxdd'],'positive_matched_folds':sum(z['excess_cagr_vs_always_intraday']>0 for z in folds),'folds':folds}
  out['tests'][name]=d
 z=out['tests']['2020']['costs']['5']; out['decision']='P96_OVERNIGHT_GAP_REVERSAL_SUPPORTED' if z['excess_cagr_vs_always_intraday']>0 and z['positive_matched_folds']>=3 and z['sharpe_delta_vs_always_intraday']>0 else 'P96_OVERNIGHT_GAP_REVERSAL_NOT_SUPPORTED'; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p96_overnight_gap_reversal_r1.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out))
if __name__=='__main__': main()
