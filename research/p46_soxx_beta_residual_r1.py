from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

P46=tuple(p46.SYMBOLS); SEMI=('SOXX','QQQ'); ALL=tuple(dict.fromkeys((*P46,'SOXX')))

def fit(y,X):
    y=np.asarray(y,float); X=np.asarray(X,float); Z=np.column_stack([np.ones(len(y)),X]); coef=np.linalg.lstsq(Z,y,rcond=None)[0]; resid=y-Z@coef
    return {'monthly_intercept':float(coef[0]),'annualized_intercept':float(coef[0]*12),'betas':[float(x) for x in coef[1:]],'r2':float(1-(resid@resid)/((y-y.mean())@(y-y.mean()))) if len(y)>2 else 0.0,'resid_ann_vol':float(np.std(resid,ddof=1)*np.sqrt(12))}

def boot(y,X,reps=4000,block=12,seed=1):
    y=np.asarray(y,float); X=np.asarray(X,float); n=len(y); rng=np.random.default_rng(seed); vals=[]
    for _ in range(reps):
      ids=[]
      while len(ids)<n:
        st=int(rng.integers(0,max(1,n-block+1))); ids.extend(range(st,min(st+block,n)))
      ids=np.array(ids[:n]); vals.append(fit(y[ids],X[ids])['annualized_intercept'])
    a=np.asarray(vals); return {'replicates':reps,'block_months':block,'bootstrap_95pct':[float(np.quantile(a,.025)),float(np.quantile(a,.975))],'p_alpha_le_zero':float((a<=0).mean())}

def main():
    close=base.load(ALL); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]
    panel,m=p46.feature_panel(close[list(P46)],p46.FACTORS); sm=close[list(SEMI)].resample('ME').last(); mom=sm.pct_change(6); s46={}; ss={}
    for dt in sorted(panel.month.unique()):
      b=panel[panel.month==dt].sort_values(['score','symbol'],ascending=[False,True])
      if len(b)==len(P46):
        c=set(b.head(2).symbol.tolist()); s46[pd.Timestamp(dt)]={s:(.5 if s in c else 0.) for s in P46}
    for dt in mom.index:
      if mom.loc[dt].isna().any(): continue
      p='SOXX' if mom.at[dt,'SOXX']>mom.at[dt,'QQQ'] else 'QQQ'; ss[pd.Timestamp(dt)]={'SOXX':1. if p=='SOXX' else 0.,'QQQ':1. if p=='QQQ' else 0.}
    daily=close.index; labels=[pd.Timestamp(x) for x in m.index if pd.Timestamp(x) in s46 and pd.Timestamp(x) in ss]; rec=[]; p46prev={s:0. for s in P46}; sprev={s:0. for s in SEMI}; bp=50; delay=1
    for i in range(len(labels)-1):
      dt,nxt=labels[i],labels[i+1]; a0=daily[daily<=dt]; z0=daily[daily<=nxt]
      if not len(a0) or not len(z0): continue
      a=int(daily.get_loc(a0[-1]))+delay; z=int(daily.get_loc(z0[-1]))+delay
      if z>=len(daily): continue
      r46=close.loc[daily[z],list(P46)]/close.loc[daily[a],list(P46)]-1; rs=close.loc[daily[z],list(SEMI)]/close.loc[daily[a],list(SEMI)]-1; w46=s46[dt]; ws=ss[dt]
      t46=.5*sum(abs(w46[s]-p46prev[s]) for s in P46); ts=.5*sum(abs(ws[s]-sprev[s]) for s in SEMI)
      g46=sum(w46[s]*float(r46[s]) for s in P46); gs=sum(ws[s]*float(rs[s]) for s in SEMI)
      cand=.5*(g46-t46*bp/10000)+.5*(gs-ts*bp/10000); matched=.5*float(r46.mean())+.25*float(rs.SOXX+rs.QQQ)
      rec.append((daily[z],cand,matched,float(rs.QQQ),float((close.loc[daily[z],'SPY']/close.loc[daily[a],'SPY'])-1))); p46prev=w46; sprev=ws
    f=pd.DataFrame(rec,columns=['date','candidate','matched','qqq','spy']).set_index('date'); tests={}
    for label,g in [('full',f),('2022_forward',f[f.index>=pd.Timestamp('2022-01-01')])]:
      y=g.candidate-g.matched; X=np.column_stack([g.qqq,g.spy]); r=fit(y,X); r['bootstrap']=boot(y,X,reps=4000,block=12,seed=20260909+len(g)); r['months']=len(g); tests[label]=r
    state='P46_SOXX_BETA_RESIDUAL_SUPPORTED' if tests['full']['annualized_intercept']>0 and tests['full']['bootstrap']['p_alpha_le_zero']<=.1 and tests['2022_forward']['annualized_intercept']>0 else 'P46_SOXX_BETA_RESIDUAL_NOT_SUPPORTED'
    out={'schema':'research.p46_soxx_beta_residual_r1','parents':['P46','P36_SOXX_REPRESENTATION'],'scientific_contract':{'candidate':'fixed 50% P46 + 50% frozen 6m SOXX-vs-QQQ sleeve','execution_delay_trading_days':1,'cost_bps':50,'matched_control':'exact same-interval P46 EW plus static SOXX/QQQ control','factor_controls':['QQQ','SPY'],'windows':['full','2022-forward'],'bootstrap':'4000 12-month moving blocks','no_parameter_or_weight_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_soxx_beta_residual_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
