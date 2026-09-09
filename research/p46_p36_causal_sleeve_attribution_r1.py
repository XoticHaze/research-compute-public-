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
def main():
 close=base.load(ALL); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]; panel,m=p46.feature_panel(close[list(P46)],p46.FACTORS); m36=close[list(P36)].resample('ME').last(); mom=m36.pct_change(6); s46={}; s36={}
 for dt in sorted(panel.month.unique()):
  b=panel[panel.month==dt].sort_values(['score','symbol'],ascending=[False,True]);
  if len(b)==len(P46):
   c=set(b.head(2).symbol.tolist()); s46[pd.Timestamp(dt)]={s:(.5 if s in c else 0.) for s in P46}
 for dt in mom.index:
  if mom.loc[dt].isna().any(): continue
  p='SMH' if mom.at[dt,'SMH']>mom.at[dt,'QQQ'] else 'QQQ'; s36[pd.Timestamp(dt)]={'SMH':1. if p=='SMH' else 0.,'QQQ':1. if p=='QQQ' else 0.}
 daily=close.index; labels=[pd.Timestamp(x) for x in m.index if pd.Timestamp(x) in s46 and pd.Timestamp(x) in s36]; tests={}
 for delay in (1,3,5):
  tests[str(delay)]={}
  for bp in (25,50,100):
   prev46={s:0. for s in P46}; prev36={s:0. for s in P36}; rec=[]
   for i in range(len(labels)-1):
    dt,nxt=labels[i],labels[i+1]; a0=daily[daily<=dt]; z0=daily[daily<=nxt]
    if not len(a0) or not len(z0): continue
    a=int(daily.get_loc(a0[-1]))+delay; z=int(daily.get_loc(z0[-1]))+delay
    if z>=len(daily) or a>=len(daily): continue
    r46=close.loc[daily[z],list(P46)]/close.loc[daily[a],list(P46)]-1; r36=close.loc[daily[z],list(P36)]/close.loc[daily[a],list(P36)]-1; w46=s46[dt]; w36=s36[dt]; t46=.5*sum(abs(w46[s]-prev46[s]) for s in P46); t36=.5*sum(abs(w36[s]-prev36[s]) for s in P36); g46=sum(w46[s]*float(r46[s]) for s in P46); g36=sum(w36[s]*float(r36[s]) for s in P36); rec.append((daily[z],g46-t46*bp/10000,float(r46.mean()),g36-t36*bp/10000,.5*float(r36.SMH+r36.QQQ))); prev46=w46; prev36=w36
   f=pd.DataFrame(rec,columns=['date','p46','p46m','p36','p36m']).set_index('date'); e46=cagr(f.p46)-cagr(f.p46m); e36=cagr(f.p36)-cagr(f.p36m); blend=cagr(.5*f.p46+.5*f.p36)-cagr(.5*f.p46m+.5*f.p36m); tests[str(delay)][str(bp)]={'p46_excess_cagr':e46,'p36_excess_cagr':e36,'blend_excess_cagr':blend,'months':len(f)}
 d=tests['1']['50']; state='BOTH_SLEEVES_CAUSALLY_POSITIVE' if d['p46_excess_cagr']>0 and d['p36_excess_cagr']>0 else 'CAUSAL_SUPPORT_CONCENTRATED_BY_SLEEVE'
 out={'schema':'research.p46_p36_causal_sleeve_attribution_r1','parents':['P46','P36'],'scientific_contract':{'test':'attribute same post-month-end entry-delay excess to P46 and P36 sleeves separately','delays_trading_days':[1,3,5],'costs_bps':[25,50,100],'matched_controls':['P46 same-universe equal weight','P36 static 50/50 SMH-QQQ'],'no_weight_or_parameter_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_causal_sleeve_attribution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':state,'d1_50':d},sort_keys=True))
if __name__=='__main__': main()
