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
    rows={}
    for w in (36,60):
        vals=[]
        for end in range(w,len(idx)+1):
            sl=slice(end-w,end); ix=idx[sl]; y=active.iloc[sl]; X=np.column_stack([q.loc[ix],s.loc[ix]]); r=beta.fit(y,X)
            vals.append((ix[-1],r['annualized_intercept']))
        z=pd.Series([v for _,v in vals],index=[d for d,_ in vals],dtype=float)
        rows[str(w)]={'windows':int(len(z)),'positive_fraction':float((z>0).mean()),'median_annualized_intercept':float(z.median()),'p10_annualized_intercept':float(z.quantile(.10)),'worst_annualized_intercept':float(z.min()),'recent_annualized_intercept':float(z.iloc[-1])}
    state='BETA_RESIDUAL_ROLLING_PERSISTENCE_SUPPORTED' if rows['36']['positive_fraction']>=.7 and rows['60']['positive_fraction']>=.7 and rows['60']['median_annualized_intercept']>0 else 'BETA_RESIDUAL_ROLLING_PERSISTENCE_MIXED'
    out={'schema':'research.p46_p36_beta_residual_rolling_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'fixed 50% P46 + 50% P36','active_return':'candidate minus exact matched blend','factor_controls':['QQQ','SPY'],'cost_bps':50,'rolling_windows_months':[36,60],'regression':'monthly OLS active return on QQQ and SPY with intercept','no_parameter_or_weight_tuning':True,'opportunity_question':'whether residual matched alpha persists through time despite raw all-in QQQ opportunity-cost caution'},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':rows,'decision':state}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_beta_residual_rolling_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
