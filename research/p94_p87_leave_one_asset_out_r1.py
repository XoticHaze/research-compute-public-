from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
SYMS=("VTI","VEA","IEF","IAU","GSG"); REQ=(*SYMS,"SPY","QQQ"); START="2007-01-01"
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; return {'cagr':c,'annualized_mean':a,'annualized_vol':v,'sharpe_rf0':a/v if v else None,'max_drawdown_monthly':float(d.min())}
def fold_positive(x,n=5):
 a=np.array_split(np.arange(len(x)),n); return sum(float(x.iloc[i].mean())>0 for i in a if len(i))
def build(universe,bps):
 d=yf.download(list(REQ),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(REQ)].dropna(how='all').astype(float); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=close.resample('ME').last(); m=m.loc[m.index<=last.normalize()]; trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); prev={s:0. for s in universe}; rows=[]
 for dt in m.index:
  b=pd.DataFrame({'mom6':mom.loc[dt,list(universe)],'trend200':trend.loc[dt,list(universe)],'drawdown6':dd.loc[dt,list(universe)]},index=list(universe))
  if b.isna().any().any(): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list(REQ)]/m.loc[dt,list(REQ)]-1
  if r.isna().any(): continue
  score=b.rank(axis=0,pct=True,method='average').mean(axis=1); chosen=score.sort_values(ascending=False).head(2).index; w={s:(.5 if s in chosen else 0.) for s in universe}; turn=.5*sum(abs(w[s]-prev[s]) for s in universe); strat=sum(w[s]*float(r[s]) for s in universe)-turn*bps/10000; ew=float(r.loc[list(universe)].mean()); rows.append({'date':nxt,'strategy':strat,'ew':ew,'excess':strat-ew}); prev=w
 return pd.DataFrame(rows).set_index('date')
def main():
 results={}; pass25=pass50=0
 for omitted in SYMS:
  u=tuple(s for s in SYMS if s!=omitted); results[omitted]={}
  for bps in (25,50):
   f=build(u,bps); sm=metrics(f.strategy); ew=metrics(f.ew); ex=sm['cagr']-ew['cagr']; rec={'universe':u,'months':len(f),'strategy':sm,'matched_equal_weight':ew,'excess_cagr_vs_ew':ex,'positive_chronological_folds':fold_positive(f.excess,5)}; results[omitted][str(bps)]=rec
  pass25+=results[omitted]['25']['excess_cagr_vs_ew']>0; pass50+=results[omitted]['50']['excess_cagr_vs_ew']>0
 out={'schema':'research.p94_p87_leave_one_asset_out_r1','parent_ids':['P46','P87','P91','P94'],'contract':{'mechanism':'frozen P87 momentum+trend+drawdown top2 recomputed after each single-asset omission','universe':SYMS,'costs_bps':[25,50],'matched_control':'equal weight of same remaining assets','no_parameter_tuning':True},'results':results,'positive_omissions_25bps':int(pass25),'positive_omissions_50bps':int(pass50),'decision':'EDGE_NOT_SINGLE_ASSET_DEPENDENT' if pass25>=4 and pass50>=3 else 'ASSET_DEPENDENCE_CAUTION'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p94_p87_leave_one_asset_out_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'positive25':int(pass25),'positive50':int(pass50),'results':{k:{b:{'excess':v[b]['excess_cagr_vs_ew'],'folds':v[b]['positive_chronological_folds']} for b in ('25','50')} for k,v in results.items()}},sort_keys=True))
if __name__=='__main__': main()
