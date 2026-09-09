from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
P46=tuple(p46.SYMBOLS); P36=('SMH','QQQ'); ALL=tuple(dict.fromkeys((*P46,'SMH')))
def cagr(x):
 x=pd.Series(x,dtype=float).dropna(); return float((1+x).prod()**(12/len(x))-1)
def build(close,bp=50,delay=1):
 panel,m=p46.feature_panel(close[list(P46)],p46.FACTORS); mm=close[list(P36)].resample('ME').last(); mom=mm.pct_change(6); s46={}; s36={}
 for dt in sorted(panel.month.unique()):
  b=panel[panel.month==dt].sort_values(['score','symbol'],ascending=[False,True]);
  if len(b)==len(P46):
   c=set(b.head(2).symbol.tolist()); s46[pd.Timestamp(dt)]={s:(.5 if s in c else 0.) for s in P46}
 for dt in mom.index:
  if mom.loc[dt].isna().any(): continue
  p='SMH' if mom.at[dt,'SMH']>mom.at[dt,'QQQ'] else 'QQQ'; s36[pd.Timestamp(dt)]={'SMH':1. if p=='SMH' else 0.,'QQQ':1. if p=='QQQ' else 0.}
 daily=close.index; labels=[pd.Timestamp(x) for x in m.index if pd.Timestamp(x) in s46 and pd.Timestamp(x) in s36]; a46={s:0. for s in P46}; a36={s:0. for s in P36}; rec=[]
 for i in range(len(labels)-1):
  dt,nxt=labels[i],labels[i+1]; x=daily[daily<=dt]; y=daily[daily<=nxt]
  if not len(x) or not len(y): continue
  a=int(daily.get_loc(x[-1]))+delay; z=int(daily.get_loc(y[-1]))+delay
  if z>=len(daily) or a>=len(daily): continue
  r46=close.loc[daily[z],list(P46)]/close.loc[daily[a],list(P46)]-1; r36=close.loc[daily[z],list(P36)]/close.loc[daily[a],list(P36)]-1; w46=s46[dt]; w36=s36[dt]; t46=.5*sum(abs(w46[s]-a46[s]) for s in P46); t36=.5*sum(abs(w36[s]-a36[s]) for s in P36); cand=.5*(sum(w46[s]*float(r46[s]) for s in P46)-t46*bp/10000)+.5*(sum(w36[s]*float(r36[s]) for s in P36)-t36*bp/10000); matched=.5*float(r46.mean())+.25*float(r36.SMH+r36.QQQ); rec.append((daily[z],cand,matched,float(r46.QQQ))); a46=w46; a36=w36
 return pd.DataFrame(rec,columns=['date','candidate','matched','qqq']).set_index('date')
def score(f):
 pos=0
 for ids in np.array_split(np.arange(len(f)),min(5,len(f))):
  q=f.iloc[ids]; pos+=cagr(q.candidate)-cagr(q.matched)>0
 return {'months':len(f),'start':str(f.index.min().date()),'end':str(f.index.max().date()),'excess_vs_matched_cagr':cagr(f.candidate)-cagr(f.matched),'excess_vs_qqq_cagr':cagr(f.candidate)-cagr(f.qqq),'positive_folds':int(pos)}
def main():
 close=base.load(ALL); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]; tests={}
 for bp in (50,100):
  full=build(close,bp,1); tests[str(bp)]={k:score(full.loc[pd.Timestamp(start):]) for k,start in [('2015','2015-01-01'),('2020','2020-01-01'),('2022','2022-01-01')]}
 d=tests['50']; state='CAUSAL_RECENT_TEMPORAL_SUPPORT' if d['2015']['excess_vs_matched_cagr']>0 and d['2020']['excess_vs_matched_cagr']>0 and d['2022']['excess_vs_matched_cagr']>0 and d['2022']['positive_folds']>=3 else 'CAUSAL_RECENT_TEMPORAL_CAUTION'; out={'schema':'research.p46_p36_causal_temporal_holdout_r1','parents':['P46','P36'],'scientific_contract':{'implementation':'fixed one-trading-day delayed entry','costs_bps':[50,100],'holdouts':['2015-forward','2020-forward','2022-forward'],'comparators':['exact blended matched','QQQ'],'no_parameter_or_weight_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_causal_temporal_holdout_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':state,'tests':tests},sort_keys=True))
if __name__=='__main__': main()
