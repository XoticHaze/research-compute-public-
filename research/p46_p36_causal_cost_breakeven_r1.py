from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
P46=tuple(p46.SYMBOLS); P36=('SMH','QQQ'); ALL=tuple(dict.fromkeys((*P46,'SMH')))
def cagr(x):
 x=pd.Series(x,dtype=float).dropna(); return float((1+x).prod()**(12/len(x))-1)
def gross(close):
 panel,m=p46.feature_panel(close[list(P46)],p46.FACTORS); mm=close[list(P36)].resample('ME').last(); mom=mm.pct_change(6); s46={}; s36={}
 for dt in sorted(panel.month.unique()):
  b=panel[panel.month==dt].sort_values(['score','symbol'],ascending=[False,True])
  if len(b)==len(P46):
   c=set(b.head(2).symbol.tolist()); s46[pd.Timestamp(dt)]={s:(.5 if s in c else 0.) for s in P46}
 for dt in mom.index:
  if mom.loc[dt].isna().any(): continue
  p='SMH' if mom.at[dt,'SMH']>mom.at[dt,'QQQ'] else 'QQQ'; s36[pd.Timestamp(dt)]={'SMH':1. if p=='SMH' else 0.,'QQQ':1. if p=='QQQ' else 0.}
 daily=close.index; labels=[pd.Timestamp(x) for x in m.index if pd.Timestamp(x) in s46 and pd.Timestamp(x) in s36]; prev46={s:0. for s in P46}; prev36={s:0. for s in P36}; rec=[]
 for i in range(len(labels)-1):
  dt,nxt=labels[i],labels[i+1]; x=daily[daily<=dt]; y=daily[daily<=nxt]
  if not len(x) or not len(y): continue
  a=int(daily.get_loc(x[-1]))+1; z=int(daily.get_loc(y[-1]))+1
  if z>=len(daily): continue
  r46=close.loc[daily[z],list(P46)]/close.loc[daily[a],list(P46)]-1; r36=close.loc[daily[z],list(P36)]/close.loc[daily[a],list(P36)]-1; w46=s46[dt]; w36=s36[dt]; t46=.5*sum(abs(w46[s]-prev46[s]) for s in P46); t36=.5*sum(abs(w36[s]-prev36[s]) for s in P36); g=.5*sum(w46[s]*float(r46[s]) for s in P46)+.5*sum(w36[s]*float(r36[s]) for s in P36); turn=.5*t46+.5*t36; matched=.5*float(r46.mean())+.25*float(r36.SMH+r36.QQQ); rec.append((daily[z],g,turn,matched,float(r46.QQQ))); prev46=w46; prev36=w36
 return pd.DataFrame(rec,columns=['date','gross','turnover','matched','qqq']).set_index('date')
def main():
 close=base.load(ALL); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]; f=gross(close); rows=[]
 for bp in range(0,301,5):
  cand=f.gross-f.turnover*bp/10000; rows.append({'bps':bp,'candidate_cagr':cagr(cand),'excess_matched':cagr(cand)-cagr(f.matched),'excess_qqq':cagr(cand)-cagr(f.qqq)})
 bm=next((r['bps'] for r in rows if r['excess_matched']<=0),None); bq=next((r['bps'] for r in rows if r['excess_qqq']<=0),None); by={r['bps']:r for r in rows}; state='CAUSAL_COST_CAPACITY_QQQ_THIN' if bq is not None and bq<100 else 'CAUSAL_COST_CAPACITY_ROBUST_TO_100BPS'; out={'schema':'research.p46_p36_causal_cost_breakeven_r1','parents':['P46','P36'],'scientific_contract':{'implementation':'fixed one-trading-day delayed entry','cost_grid_bps':'0..300 step 5','comparators':['exact matched blend','QQQ'],'no_parameter_or_weight_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'annual_turnover':float(f.turnover.mean()*12),'break_even_matched_bps':bm,'break_even_qqq_bps':bq,'at_50':by[50],'at_100':by[100],'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_causal_cost_breakeven_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
