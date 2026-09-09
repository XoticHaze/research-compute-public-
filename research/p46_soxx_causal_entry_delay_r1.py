from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
P46=tuple(p46.SYMBOLS); SEMI=('SOXX','QQQ'); ALL=tuple(dict.fromkeys((*P46,'SOXX')))
def cagr(x):
 x=pd.Series(x,dtype=float).dropna(); return float((1+x).prod()**(12/len(x))-1)
def main():
 close=base.load(ALL); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]; panel,m=p46.feature_panel(close[list(P46)],p46.FACTORS); sm=close[list(SEMI)].resample('ME').last(); mom=sm.pct_change(6); s46={}; ss={}
 for dt in sorted(panel.month.unique()):
  b=panel[panel.month==dt].sort_values(['score','symbol'],ascending=[False,True]);
  if len(b)==len(P46):
   c=set(b.head(2).symbol.tolist()); s46[pd.Timestamp(dt)]={s:(.5 if s in c else 0.) for s in P46}
 for dt in mom.index:
  if mom.loc[dt].isna().any(): continue
  p='SOXX' if mom.at[dt,'SOXX']>mom.at[dt,'QQQ'] else 'QQQ'; ss[pd.Timestamp(dt)]={'SOXX':1. if p=='SOXX' else 0.,'QQQ':1. if p=='QQQ' else 0.}
 daily=close.index; labels=[pd.Timestamp(x) for x in m.index if pd.Timestamp(x) in s46 and pd.Timestamp(x) in ss]; tests={}
 for delay in (1,3,5):
  tests[str(delay)]={}
  for bp in (25,50,100):
   p46prev={s:0. for s in P46}; sprev={s:0. for s in SEMI}; rec=[]
   for i in range(len(labels)-1):
    dt,nxt=labels[i],labels[i+1]; a0=daily[daily<=dt]; z0=daily[daily<=nxt]
    if not len(a0) or not len(z0): continue
    a=int(daily.get_loc(a0[-1]))+delay; z=int(daily.get_loc(z0[-1]))+delay
    if z>=len(daily) or a>=len(daily): continue
    r46=close.loc[daily[z],list(P46)]/close.loc[daily[a],list(P46)]-1; rs=close.loc[daily[z],list(SEMI)]/close.loc[daily[a],list(SEMI)]-1; w46=s46[dt]; ws=ss[dt]; t46=.5*sum(abs(w46[s]-p46prev[s]) for s in P46); ts=.5*sum(abs(ws[s]-sprev[s]) for s in SEMI); g46=sum(w46[s]*float(r46[s]) for s in P46); gs=sum(ws[s]*float(rs[s]) for s in SEMI); cand=.5*(g46-t46*bp/10000)+.5*(gs-ts*bp/10000); matched=.5*float(r46.mean())+.25*float(rs.SOXX+rs.QQQ); rec.append((daily[z],cand,matched)); p46prev=w46; sprev=ws
   f=pd.DataFrame(rec,columns=['date','candidate','matched']).set_index('date'); pos=0
   for ids in np.array_split(np.arange(len(f)),5):
    q=f.iloc[ids]; pos+=cagr(q.candidate)-cagr(q.matched)>0
   tests[str(delay)][str(bp)]={'months':len(f),'excess_cagr':cagr(f.candidate)-cagr(f.matched),'positive_folds':int(pos)}
 d=tests['1']['50']; state='P46_SOXX_CAUSAL_ENTRY_DELAY_SUPPORTED' if d['excess_cagr']>0 and d['positive_folds']>=3 and tests['3']['50']['excess_cagr']>0 else 'P46_SOXX_CAUSAL_ENTRY_DELAY_WEAK'; out={'schema':'research.p46_soxx_causal_entry_delay_r1','parents':['P46','P36_SOXX_REPRESENTATION'],'scientific_contract':{'candidate':'fixed 50% P46 + 50% frozen 6m SOXX-vs-QQQ sleeve','delays_trading_days':[1,3,5],'costs_bps':[25,50,100],'matched_control':'exact same-interval P46 EW plus static SOXX/QQQ control','no_parameter_or_weight_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_soxx_causal_entry_delay_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':state,'tests':tests},sort_keys=True))
if __name__=='__main__': main()
