from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
import p46_p36_combined_alpha_r1 as combo

def summarize(x,y):
    x=pd.Series(x,dtype=float); y=pd.Series(y,dtype=float); z=.5*x+.5*y
    vx=float(x.var(ddof=0)); vy=float(y.var(ddof=0)); vz=float(z.var(ddof=0)); cov=float(x.cov(y,ddof=0)); corr=float(x.corr(y))
    weighted_standalone_vol=.5*np.sqrt(vx)+.5*np.sqrt(vy); blend_vol=np.sqrt(vz)
    return {'correlation':corr,'covariance':cov,'p46_ann_mean_active':float(x.mean()*12),'p36_ann_mean_active':float(y.mean()*12),'blend_ann_mean_active':float(z.mean()*12),'p46_ann_active_vol':float(x.std(ddof=0)*np.sqrt(12)),'p36_ann_active_vol':float(y.std(ddof=0)*np.sqrt(12)),'blend_ann_active_vol':float(z.std(ddof=0)*np.sqrt(12)),'diversification_ratio':float(weighted_standalone_vol/blend_vol) if blend_vol>0 else None,'same_sign_fraction':float((np.sign(x)==np.sign(y)).mean()),'both_positive_fraction':float(((x>0)&(y>0)).mean()),'one_positive_one_negative_fraction':float((((x>0)&(y<0))|((x<0)&(y>0))).mean())}

def main():
    syms=tuple(dict.fromkeys((*p46.SYMBOLS,'SMH'))); close=base.load(syms)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<current_month_start]
    a=p46.returns(close,p46.FACTORS); b=combo.p36_frame(close); idx=a.index.intersection(b.index); a=a.loc[idx]; b=b.loc[idx]; tests={}
    for label,ix in [('full',idx),('2022_forward',idx[idx>=pd.Timestamp('2022-01-01')])]:
        tests[label]={}
        for bp in (25,50,100):
            p46_active=(a.loc[ix].gross-a.loc[ix].turnover*bp/10000)-a.loc[ix].ew
            p36_active=(b.loc[ix].gross-b.loc[ix].turnover*bp/10000)-b.loc[ix].matched
            tests[label][str(bp)]=summarize(p46_active,p36_active)
    f=tests['full']['50']; supported=f['correlation']<0.5 and f['diversification_ratio']>1.05 and f['p46_ann_mean_active']>0 and f['p36_ann_mean_active']>0
    out={'schema':'research.p46_p36_active_orthogonality_r1','parents':['P46','P36'],'scientific_contract':{'test':'active-return correlation/covariance and diversification of P46 vs P36 relative to their exact matched controls','costs_bps_applied_per_sleeve':[25,50,100],'windows':['full','2022-forward'],'incomplete_months_excluded':True,'no_weight_or_parameter_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'window':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':len(idx)},'tests':tests,'decision':'P46_P36_ACTIVE_RETURNS_ORTHOGONAL_ENOUGH' if supported else 'P46_P36_ACTIVE_RETURNS_NOT_ORTHOGONAL'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_active_orthogonality_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'full50':f,'recent50':tests['2022_forward']['50']},sort_keys=True))
if __name__=='__main__': main()
