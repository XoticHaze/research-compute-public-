from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
P46=tuple(p46.SYMBOLS); P36=('SMH','QQQ'); ALL=tuple(dict.fromkeys((*P46,'SMH')))
def metrics(x):
 x=pd.Series(x,dtype=float).dropna(); eq=(1+x).cumprod(); c=float(eq.iloc[-1]**(12/len(x))-1); vol=float(x.std(ddof=0)*np.sqrt(12)); sh=float(x.mean()*12/vol) if vol>0 else 0.; dd=float((eq/eq.cummax()-1).min()); return {'cagr':c,'ann_vol':vol,'sharpe0':sh,'max_drawdown':dd}
def main():
 close=base.load(ALL); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]; panel,m=p46.feature_panel(close[list(P46)],p46.FACTORS); mm=close[list(P36)].resample('ME').last(); mom=mm.pct_change(6); s46={}; s36={}
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
  for bp in (50,100):
   a46={s:0. for s in P46}; a36={s:0. for s in P36}; rec=[]
   for i in range(len(labels)-1):
    dt,nxt=labels[i],labels[i+1]; x=daily[daily<=dt]; y=daily[daily<=nxt]
    if not len(x) or not len(y): continue
    a=int(daily.get_loc(x[-1]))+delay; z=int(daily.get_loc(y[-1]))+delay
    if z>=len(daily) or a>=len(daily): continue
    r46=close.loc[daily[z],list(P46)]/close.loc[daily[a],list(P46)]-1; r36=close.loc[daily[z],list(P36)]/close.loc[daily[a],list(P36)]-1; w46=s46[dt]; w36=s36[dt]; t46=.5*sum(abs(w46[s]-a46[s]) for s in P46); t36=.5*sum(abs(w36[s]-a36[s]) for s in P36); g46=sum(w46[s]*float(r46[s]) for s in P46); g36=sum(w36[s]*float(r36[s]) for s in P36); cand=.5*(g46-t46*bp/10000)+.5*(g36-t36*bp/10000); matched=.5*float(r46.mean())+.25*float(r36.SMH+r36.QQQ); rec.append((daily[z],cand,matched,float(r46.QQQ),float(r46.SPY))); a46=w46; a36=w36
   f=pd.DataFrame(rec,columns=['date','candidate','matched','qqq','spy']).set_index('date'); cm=metrics(f.candidate); qm=metrics(f.qqq); sm=metrics(f.spy); bm=metrics(f.matched); tests[str(delay)][str(bp)]={'months':len(f),'candidate':cm,'matched':bm,'qqq':qm,'spy':sm,'excess_vs_matched_cagr':cm['cagr']-bm['cagr'],'excess_vs_qqq_cagr':cm['cagr']-qm['cagr'],'excess_vs_spy_cagr':cm['cagr']-sm['cagr']}
 d=tests['1']['50']; state='CAUSAL_BLEND_CLEARS_QQQ_AND_SPY' if d['excess_vs_qqq_cagr']>0 and d['excess_vs_spy_cagr']>0 else 'CAUSAL_BLEND_OPPORTUNITY_COST_CAUTION'; out={'schema':'research.p46_p36_causal_opportunity_cost_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'fixed 50% P46 + 50% P36','causal_delays_trading_days':[1,3,5],'costs_bps':[50,100],'comparators':['exact blended matched control','QQQ buy-and-hold same intervals','SPY buy-and-hold same intervals'],'risk_metrics':['annualized volatility','Sharpe rf=0','max drawdown'],'no_parameter_or_weight_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_causal_opportunity_cost_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':state,'d1_50':d},sort_keys=True))
if __name__=='__main__': main()
