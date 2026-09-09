from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base

SYMS=base.UNIVERSES['industry']

def build(close:pd.DataFrame)->pd.DataFrame:
 m=close.resample('ME').last(); last=pd.Timestamp(close.index.max()); last=last.tz_localize(None) if last.tzinfo is not None else last; m=m.loc[m.index<=last.normalize()]; dr=close.pct_change(); vol=(dr.rolling(126,min_periods=100).std(ddof=0)*np.sqrt(252)).resample('ME').last(); trend=(close/close.rolling(200,min_periods=160).mean()-1).resample('ME').last(); dd=(close/close.rolling(126,min_periods=100).max()-1).resample('ME').last(); mom=m.pct_change(6); prev={s:0. for s in SYMS}; rows=[]
 for dt in m.index:
  b=pd.DataFrame({'mom6':mom.loc[dt,list(SYMS)],'trend200':trend.loc[dt,list(SYMS)],'low_vol6':-vol.loc[dt,list(SYMS)],'drawdown6':dd.loc[dt,list(SYMS)]},index=list(SYMS))
  if b.isna().any().any(): continue
  loc=m.index.get_loc(dt)
  if not isinstance(loc,(int,np.integer)) or loc+1>=len(m): continue
  nxt=m.index[loc+1]; r=m.loc[nxt,list((*SYMS,'SPY','QQQ'))]/m.loc[dt,list((*SYMS,'SPY','QQQ'))]-1
  if r.isna().any(): continue
  score=b.rank(axis=0,pct=True,method='average').mean(axis=1); chosen=score.sort_values(ascending=False).head(3).index; w={s:(1/3 if s in chosen else 0.) for s in SYMS}; turnover=.5*sum(abs(w[s]-prev[s]) for s in SYMS); rows.append({'date':nxt,'gross':sum(w[s]*float(r[s]) for s in SYMS),'turnover':turnover,'ew':float(r.loc[list(SYMS)].mean()),'spy':float(r.SPY),'qqq':float(r.QQQ)}); prev=w
 return pd.DataFrame(rows).set_index('date')

def cagr(r):
 r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)
def rolling(c,b,w):
 vals=[cagr(c.iloc[i-w:i])-cagr(b.iloc[i-w:i]) for i in range(w,len(c)+1)]; a=np.asarray(vals); return {'windows':len(a),'positive_fraction':float((a>0).mean()),'median_excess_cagr':float(np.median(a)),'p10_excess_cagr':float(np.quantile(a,.1)),'p90_excess_cagr':float(np.quantile(a,.9))}
def bootstrap(c,b,n=5000,block=12):
 x=(c-b).to_numpy(); rng=np.random.default_rng(20260909); vals=[]; L=len(x)
 for _ in range(n):
  pieces=[]
  while sum(len(z) for z in pieces)<L:
   s=int(rng.integers(0,max(1,L-block+1))); pieces.append(x[s:s+block])
  vals.append(float(np.concatenate(pieces)[:L].mean()*12))
 a=np.asarray(vals); return {'annualized_mean_excess':float(x.mean()*12),'bootstrap_95pct':[float(np.quantile(a,.025)),float(np.quantile(a,.975))],'p_excess_le_zero':float((a<=0).mean()),'block_months':block,'replicates':n}
def main():
 close=base.load(SYMS); f=build(close); tests={}
 for bps in (25,50):
  c=f.gross-f.turnover*bps/10000; tests[str(bps)]={'candidate':base.metrics(c),'matched_equal_weight':base.metrics(f.ew),'spy':base.metrics(f.spy),'qqq':base.metrics(f.qqq),'rolling36':rolling(c,f.ew,36),'rolling60':rolling(c,f.ew,60),'bootstrap':bootstrap(c,f.ew)}
 p25,p50=tests['25'],tests['50']; supported=p25['rolling60']['positive_fraction']>=.6 and p25['bootstrap']['p_excess_le_zero']<=.2 and p50['bootstrap']['annualized_mean_excess']>0
 out={'schema':'research.p88_p47_serial_persistence_r1','parent_ids':['P47','P88'],'scientific_contract':{'mechanism':'original frozen P47 four-factor top3 industry composite','matched_control':'exact same-universe equal weight','opportunity_cost':['SPY','QQQ'],'costs_bps':[25,50],'rolling_windows_months':[36,60],'bootstrap':'12m moving block, 5000 reps, deterministic seed','no_parameter_tuning':True},'window':{'start':str(f.index.min().date()),'end':str(f.index.max().date()),'months':len(f)},'mean_annual_turnover':float(f.turnover.mean()*12),'tests':tests,'decision':'SUPPORTED_P47_SERIAL_PERSISTENCE' if supported else 'P47_PERSISTENCE_INSUFFICIENT_RERANK'}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p88_p47_serial_persistence_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'25':{'rolling36':p25['rolling36'],'rolling60':p25['rolling60'],'bootstrap':p25['bootstrap']},'50_bootstrap':p50['bootstrap'],'window':out['window'],'turnover':out['mean_annual_turnover']},sort_keys=True))
if __name__=='__main__': main()
