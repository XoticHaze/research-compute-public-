from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
SYMS=("VTI","VEA","IEF","IAU","GSG"); REQ=(*SYMS,"SPY","QQQ"); START="2007-01-01"
def metrics(r):
 r=pd.Series(r,dtype=float).dropna(); e=(1+r).cumprod(); y=len(r)/12; c=float(e.iloc[-1]**(1/y)-1); a=float(r.mean()*12); v=float(r.std(ddof=0)*math.sqrt(12)); d=e/e.cummax()-1; m=float(d.min()); return {'cagr':c,'annualized_mean':a,'annualized_vol':v,'sharpe_rf0':a/v if v else None,'max_drawdown_monthly':m}
def build():
 d=yf.download(list(REQ),start=START,auto_adjust=True,progress=False,threads=False); close=d['Close'] if isinstance(d.columns,pd.MultiIndex) else d[['Close']]; close=close.loc[:,list(REQ)].dropna(how='all').astype(float); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=close.resample('ME').last(); m=m.loc[m.index<=last.normalize()]; dr=close.pct_change(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); signals=[]
 for dt in m.index:
  b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':trend.loc[dt,list(SYMS)],'drawdown6':dd.loc[dt,list(SYMS)]},index=list(SYMS))
  if b.isna().any().any(): continue
  score=b.rank(axis=0,pct=True,method='average').mean(axis=1); signals.append((dt,tuple(score.sort_values(ascending=False).head(2).index)))
 sig=dict(signals); rows=[]
 for dt in m.index:
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+2>=len(m): continue
  if dt not in sig: continue
  nxt=m.index[loc+1]; nxt2=m.index[loc+2]
  r0=m.loc[nxt,list(REQ)]/m.loc[dt,list(REQ)]-1; r1=m.loc[nxt2,list(REQ)]/m.loc[nxt,list(REQ)]-1
  if r0.isna().any() or r1.isna().any(): continue
  rows.append({'signal_date':dt,'ret_date_0':nxt,'ret_date_1':nxt2,'chosen':sig[dt],'r0':r0,'r1':r1})
 return rows

def evaluate(rows,delay,bps):
 prev={s:0. for s in SYMS}; out=[]
 for x in rows:
  r=x['r0'] if delay==0 else x['r1']; chosen=x['chosen']; w={s:(.5 if s in chosen else 0.) for s in SYMS}; turn=.5*sum(abs(w[s]-prev[s]) for s in SYMS); out.append((sum(w[s]*float(r[s]) for s in SYMS)-turn*bps/10000,float(r.loc[list(SYMS)].mean()),float(r['SPY']),float(r['QQQ']))); prev=w
 return pd.DataFrame(out,columns=['strategy','ew','spy','qqq'])
def main():
 rows=build(); tests={}
 for delay in (0,1):
  tests[str(delay)]={}
  for bps in (25,50):
   f=evaluate(rows,delay,bps); sm=metrics(f.strategy); ew=metrics(f.ew); tests[str(delay)][str(bps)]={'strategy':sm,'matched_ew':ew,'excess_cagr_vs_ew':sm['cagr']-ew['cagr'],'excess_cagr_vs_spy':sm['cagr']-metrics(f.spy)['cagr'],'excess_cagr_vs_qqq':sm['cagr']-metrics(f.qqq)['cagr']}
 base=tests['0']['25']['excess_cagr_vs_ew']; lag=tests['1']['25']['excess_cagr_vs_ew']; retained=(lag/base if base!=0 else None)
 out={'schema':'research.p93_p87_signal_delay_r1','parent_ids':['P46','P87','P91','P93'],'contract':{'mechanism':'freeze P87 signal; compare immediate next-month implementation with one full month signal staleness','costs_bps':[25,50],'no_parameter_tuning':True},'rows':len(rows),'tests':tests,'retained_excess_ratio_25bps':retained,'decision':'SIGNAL_EDGE_SURVIVES_ONE_MONTH_STALENESS' if lag>0 else 'SIGNAL_EDGE_TIMING_SENSITIVE_ONE_MONTH_DELAY_FAILS'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p93_p87_signal_delay_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'immediate':tests['0']['25'],'delay1':tests['1']['25'],'retained':retained,'rows':len(rows)},sort_keys=True))
if __name__=='__main__': main()
