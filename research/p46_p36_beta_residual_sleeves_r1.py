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
    bp=50
    p46_active=a.gross-a.turnover*bp/10000-a.ew
    p36_active=b.gross-b.turnover*bp/10000-b.matched
    combo_active=.5*p46_active+.5*p36_active
    tests={}
    for label,ix in [('full',idx),('2022_forward',idx[idx>=pd.Timestamp('2022-01-01')])]:
      X=np.column_stack([q.loc[ix],s.loc[ix]]); tests[label]={}
      for name,y in [('P46',p46_active.loc[ix]),('P36',p36_active.loc[ix]),('COMBINED',combo_active.loc[ix])]:
        r=beta.fit(y,X); r['bootstrap']=beta.boot(y,X,reps=4000,block=12,seed=20260909+len(ix)+len(name)); tests[label][name]=r
    f=tests['full']; r=tests['2022_forward']
    both_full=all(f[x]['annualized_intercept']>0 and f[x]['bootstrap']['p_alpha_le_zero']<=.1 for x in ('P46','P36'))
    both_recent=all(r[x]['annualized_intercept']>0 for x in ('P46','P36'))
    state='BETA_RESIDUAL_DIVERSIFIED_ACROSS_SLEEVES' if both_full and both_recent else 'BETA_RESIDUAL_SLEEVE_CONCENTRATION_CAUTION'
    out={'schema':'research.p46_p36_beta_residual_sleeves_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'fixed 50% P46 + 50% P36','cost_bps':50,'sleeve_active_returns':['P46 net minus exact equal-weight cross-asset control','P36 net minus exact static SMH/QQQ matched control'],'factor_controls':['QQQ','SPY'],'windows':['full','2022-forward'],'bootstrap':'4000 12-month moving blocks','no_parameter_or_weight_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':state}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_beta_residual_sleeves_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
