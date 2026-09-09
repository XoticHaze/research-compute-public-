from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
import p46_p36_combined_alpha_r1 as combo
import p46_p36_beta_residual_r1 as beta

def main():
    syms=tuple(dict.fromkeys((*p46.SYMBOLS,'SMH'))); close=base.load(syms)
    ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]
    a=p46.returns(close,p46.FACTORS); b=combo.p36_frame(close); idx=a.index.intersection(b.index); a=a.loc[idx]; b=b.loc[idx]
    monthly=close.resample('ME').last(); q=monthly['QQQ'].pct_change().reindex(idx); s=monthly['SPY'].pct_change().reindex(idx)
    bp=50; cand=.5*(a.gross-a.turnover*bp/10000)+.5*(b.gross-b.turnover*bp/10000); matched=.5*a.ew+.5*b.matched; active=cand-matched
    out_tests={}
    for label,ix in [('full',idx),('2022_forward',idx[idx>=pd.Timestamp('2022-01-01')])]:
        y=active.loc[ix]; X=np.column_stack([q.loc[ix],s.loc[ix]]); full=beta.fit(y,X)
        Z=np.column_stack([np.ones(len(y)),X]); coef=np.linalg.lstsq(Z,np.asarray(y,float),rcond=None)[0]; resid=np.asarray(y,float)-Z@coef
        rank=np.argsort(resid)[::-1]; cases={}
        for n in (0,1,3,5):
            keep=np.ones(len(y),dtype=bool)
            if n: keep[rank[:n]]=False
            r=beta.fit(np.asarray(y)[keep],X[keep]); r['removed_top_positive_residual_months']=n; r['months']=int(keep.sum()); cases[str(n)]=r
        out_tests[label]={'baseline':full,'cases':cases}
    f=out_tests['full']['cases']['5']; r=out_tests['2022_forward']['cases']['3']
    state='BETA_RESIDUAL_NOT_TOP_MONTH_CONCENTRATED' if f['annualized_intercept']>0 and r['annualized_intercept']>0 else 'BETA_RESIDUAL_CONCENTRATION_CAUTION'
    out={'schema':'research.p46_p36_beta_residual_concentration_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'fixed 50% P46 + 50% P36','active_return':'candidate minus exact matched blend','factor_controls':['QQQ','SPY'],'cost_bps':50,'test':'remove ex post largest positive regression-residual months then refit only as robustness falsifier','removals':[1,3,5],'windows':['full','2022-forward'],'no_parameter_or_weight_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':out_tests,'decision':state}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_beta_residual_concentration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
