from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p47_deep_robustness_r2 as p47

SYMS=tuple(p47.BASE); FACTORS=('mom6','trend200')
def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def main():
    close=base.load(SYMS); month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<month_start]
    m,fm=p47.maps(close); sig={}
    for dt in m.index:
        b=pd.DataFrame({f:fm[f].loc[dt,list(SYMS)] for f in FACTORS},index=list(SYMS))
        if b.isna().any().any(): continue
        sc=b.rank(axis=0,pct=True,method='average').mean(axis=1); chosen=set(sc.sort_values(ascending=False).head(3).index.tolist()); sig[pd.Timestamp(dt)]={s:(1/3 if s in chosen else 0.) for s in SYMS}
    daily=close.index; tests={}
    for delay in (0,1,3,5):
      tests[str(delay)]={}
      for bp in (25,50,100):
        prev={s:0. for s in SYMS}; rec=[]; labels=[x for x in m.index if pd.Timestamp(x) in sig]
        for i in range(len(labels)-1):
          dt,nxt=pd.Timestamp(labels[i]),pd.Timestamp(labels[i+1]); a0=daily[daily<=dt]; z0=daily[daily<=nxt]
          if not len(a0) or not len(z0): continue
          a=int(daily.get_loc(a0[-1]))+delay; z=int(daily.get_loc(z0[-1]))+delay
          if z>=len(daily) or a>=len(daily) or z<=a: continue
          entry,exit_=daily[a],daily[z]; r=close.loc[exit_,list(SYMS)]/close.loc[entry,list(SYMS)]-1
          if r.isna().any(): continue
          w=sig[dt]; turn=.5*sum(abs(w[s]-prev[s]) for s in SYMS); cand=sum(w[s]*float(r[s]) for s in SYMS)-turn*bp/10000; rec.append((exit_,cand,float(r.mean()))); prev=w
        f=pd.DataFrame(rec,columns=['date','candidate','matched']).set_index('date'); folds=[]; pos=0
        for n,ids in enumerate(np.array_split(np.arange(len(f)),5),1):
          q=f.iloc[ids]; ex=cagr(q.candidate)-cagr(q.matched); pos+=ex>0; folds.append({'fold':n,'excess_cagr':ex})
        tests[str(delay)][str(bp)]={'months':len(f),'start':str(f.index.min().date()),'end':str(f.index.max().date()),'excess_cagr':cagr(f.candidate)-cagr(f.matched),'positive_folds':int(pos),'folds':folds}
    d1=tests['1']['50']; d3=tests['3']['50']; supported=d1['excess_cagr']>0 and d1['positive_folds']>=3 and d3['excess_cagr']>0
    out={'schema':'research.p47_causal_entry_delay_r1','parent':'P47','scientific_contract':{'economics':'unchanged mom6+trend200 industry top-3 monthly','signal_information':'completed month-end only','entry_delays_trading_days':[0,1,3,5],'costs_bps':[25,50,100],'matched_control':'same-industry equal weight over exact shifted intervals','no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':'P47_CAUSAL_ENTRY_DELAY_SUPPORTED' if supported else 'P47_CAUSAL_ENTRY_DELAY_WEAK'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p47_causal_entry_delay_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'tests':{d:{bp:{'excess':v['excess_cagr'],'folds':v['positive_folds']} for bp,v in z.items()} for d,z in tests.items()}},sort_keys=True))
if __name__=='__main__': main()
