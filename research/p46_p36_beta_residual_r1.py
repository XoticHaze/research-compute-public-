from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
import p46_p36_combined_alpha_r1 as combo

def fit(y,X):
    X=np.asarray(X,float); y=np.asarray(y,float); Z=np.column_stack([np.ones(len(y)),X]); b=np.linalg.lstsq(Z,y,rcond=None)[0]; resid=y-Z@b
    return {'monthly_intercept':float(b[0]),'annualized_intercept':float(b[0]*12),'betas':[float(x) for x in b[1:]],'resid_ann_vol':float(np.std(resid,ddof=0)*np.sqrt(12)),'r2':float(1-np.sum(resid**2)/np.sum((y-y.mean())**2)) if np.sum((y-y.mean())**2)>0 else 0.0}

def boot(y,X,reps=4000,block=12,seed=46362027):
    y=np.asarray(y,float); X=np.asarray(X,float); n=len(y); rng=np.random.default_rng(seed); vals=[]
    for _ in range(reps):
        ids=[]
        while len(ids)<n:
            s=int(rng.integers(0,max(1,n-block+1))); ids.extend(range(s,min(s+block,n)))
        ids=np.asarray(ids[:n]); vals.append(fit(y[ids],X[ids])['annualized_intercept'])
    a=np.asarray(vals); return {'bootstrap_95pct':[float(np.quantile(a,.025)),float(np.quantile(a,.975))],'p_alpha_le_zero':float((a<=0).mean()),'replicates':reps,'block_months':block}

def main():
    syms=tuple(dict.fromkeys((*p46.SYMBOLS,'SMH'))); close=base.load(syms)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<current_month_start]
    a=p46.returns(close,p46.FACTORS); b=combo.p36_frame(close); idx=a.index.intersection(b.index); a=a.loc[idx]; b=b.loc[idx]
    monthly=close.resample('ME').last(); q=monthly['QQQ'].pct_change().reindex(idx); s=monthly['SPY'].pct_change().reindex(idx); tests={}
    for label,ix in [('full',idx),('2022_forward',idx[idx>=pd.Timestamp('2022-01-01')])]:
        tests[label]={}
        for bp in (25,50,100):
            cand=.5*(a.loc[ix].gross-a.loc[ix].turnover*bp/10000)+.5*(b.loc[ix].gross-b.loc[ix].turnover*bp/10000); matched=.5*a.loc[ix].ew+.5*b.loc[ix].matched
            active=cand-matched; qq=q.loc[ix]; sp=s.loc[ix]
            models={
                'active_on_QQQ_SPY':(active,np.column_stack([qq,sp])),
                'candidate_on_QQQ':(cand,np.column_stack([qq])),
                'candidate_on_QQQ_SPY':(cand,np.column_stack([qq,sp])),
            }; tests[label][str(bp)]={}
            for name,(y,X) in models.items():
                r=fit(y,X); r['bootstrap']=boot(y,X,seed=46362027+bp+len(ix)+len(name)); tests[label][str(bp)][name]=r
    f=tests['full']['50']['active_on_QQQ_SPY']; supported=f['annualized_intercept']>0 and f['bootstrap']['p_alpha_le_zero']<=.1
    out={'schema':'research.p46_p36_beta_residual_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'research-only fixed 50% P46 + 50% P36','matched_control':'exact blended control','factor_controls':['QQQ','SPY'],'regression':'monthly OLS with intercept; 12m moving-block bootstrap of annualized intercept','costs_bps_applied_per_sleeve':[25,50,100],'windows':['full','2022-forward'],'incomplete_months_excluded':True,'no_weight_or_parameter_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'window':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':len(idx)},'tests':tests,'decision':'P46_P36_BETA_RESIDUAL_ALPHA_SUPPORTED' if supported else 'P46_P36_BETA_RESIDUAL_ALPHA_NOT_SUPPORTED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_beta_residual_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'full50':tests['full']['50'],'recent50':tests['2022_forward']['50']},sort_keys=True))
if __name__=='__main__': main()
