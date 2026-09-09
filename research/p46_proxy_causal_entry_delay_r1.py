from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
SYMS=('VTI','VUG','IEF','IAU','GSG'); FACTORS=('mom6','trend200','low_vol6','drawdown6')
def cagr(x):
 x=pd.Series(x,dtype=float).dropna(); return float((1+x).prod()**(12/len(x))-1)
def main():
 close=base.load(SYMS); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]; m=close.resample('ME').last(); dr=close.pct_change(); maps={'mom6':m.pct_change(6),'trend200':(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(),'low_vol6':-(dr.rolling(126,min_periods=100).std(ddof=0)*math.sqrt(252)).resample('ME').last(),'drawdown6':(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last()}; sig={}
 for dt in m.index:
  b=pd.DataFrame({f:maps[f].loc[dt,list(SYMS)] for f in FACTORS},index=list(SYMS))
  if b.isna().any().any(): continue
  sc=b.rank(axis=0,pct=True,method='average').mean(axis=1); c=set(sc.sort_values(ascending=False).head(2).index.tolist()); sig[pd.Timestamp(dt)]={s:(.5 if s in c else 0.) for s in SYMS}
 daily=close.index; labels=[pd.Timestamp(x) for x in m.index if pd.Timestamp(x) in sig]; tests={}
 for delay in (1,3,5):
  tests[str(delay)]={}
  for bp in (25,50,100):
   prev={s:0. for s in SYMS}; rec=[]
   for i in range(len(labels)-1):
    dt,nxt=labels[i],labels[i+1]; a0=daily[daily<=dt]; z0=daily[daily<=nxt]
    if not len(a0) or not len(z0): continue
    a=int(daily.get_loc(a0[-1]))+delay; z=int(daily.get_loc(z0[-1]))+delay
    if z>=len(daily) or a>=len(daily): continue
    r=close.loc[daily[z],list(SYMS)]/close.loc[daily[a],list(SYMS)]-1; w=sig[dt]; turn=.5*sum(abs(w[s]-prev[s]) for s in SYMS); cand=sum(w[s]*float(r[s]) for s in SYMS)-turn*bp/10000; rec.append((daily[z],cand,float(r.mean()))); prev=w
   f=pd.DataFrame(rec,columns=['date','candidate','matched']).set_index('date'); pos=0
   for ids in np.array_split(np.arange(len(f)),5):
    q=f.iloc[ids]; pos+=cagr(q.candidate)-cagr(q.matched)>0
   tests[str(delay)][str(bp)]={'months':len(f),'start':str(f.index.min().date()),'end':str(f.index.max().date()),'excess_cagr':cagr(f.candidate)-cagr(f.matched),'positive_folds':int(pos)}
 d=tests['1']['50']; state='P46_PROXY_CAUSAL_TRANSFER_SUPPORTED' if d['excess_cagr']>0 and d['positive_folds']>=3 and tests['3']['50']['excess_cagr']>0 else 'P46_PROXY_CAUSAL_TRANSFER_WEAK'; out={'schema':'research.p46_proxy_causal_entry_delay_r1','parent':'P46','scientific_contract':{'representation':list(SYMS),'economics':'same frozen four-factor top-2 monthly cross-asset mechanism','entry_delays_trading_days':[1,3,5],'costs_bps':[25,50,100],'matched_control':'same-proxy-universe equal weight over exact shifted intervals','no_parameter_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_proxy_causal_entry_delay_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':state,'tests':tests},sort_keys=True))
if __name__=='__main__': main()
