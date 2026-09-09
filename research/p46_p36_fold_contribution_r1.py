from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
import p46_p36_combined_alpha_r1 as combo

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)

def main():
    syms=tuple(dict.fromkeys((*p46.SYMBOLS,'SMH'))); close=base.load(syms)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<current_month_start]
    a=p46.returns(close,p46.FACTORS); b=combo.p36_frame(close); idx=a.index.intersection(b.index); a=a.loc[idx]; b=b.loc[idx]
    tests={}
    for bp in (25,50,100):
        p46net=a.gross-a.turnover*bp/10000; p36net=b.gross-b.turnover*bp/10000; blend=.5*p46net+.5*p36net; matched=.5*a.ew+.5*b.matched
        folds=[]
        for n,ids in enumerate(np.array_split(np.arange(len(idx)),5),start=1):
            ix=idx[ids]; folds.append({'fold':n,'start':str(ix.min().date()),'end':str(ix.max().date()),'months':len(ix),'p46_excess_cagr':cagr(p46net.loc[ix])-cagr(a.ew.loc[ix]),'p36_excess_cagr':cagr(p36net.loc[ix])-cagr(b.matched.loc[ix]),'blend_excess_cagr':cagr(blend.loc[ix])-cagr(matched.loc[ix]),'p46_ann_mean_active':float((p46net.loc[ix]-a.ew.loc[ix]).mean()*12),'p36_ann_mean_active':float((p36net.loc[ix]-b.matched.loc[ix]).mean()*12),'blend_ann_mean_active':float((blend.loc[ix]-matched.loc[ix]).mean()*12)})
        tests[str(bp)]={'folds':folds,'p46_positive_folds':sum(x['p46_excess_cagr']>0 for x in folds),'p36_positive_folds':sum(x['p36_excess_cagr']>0 for x in folds),'blend_positive_folds':sum(x['blend_excess_cagr']>0 for x in folds)}
    f=tests['50']; supported=f['blend_positive_folds']>=4 and f['p46_positive_folds']>=3 and f['p36_positive_folds']>=3
    out={'schema':'research.p46_p36_fold_contribution_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'research-only fixed 50% P46 + 50% P36','matched_control':'exact blended matched control','test':'five chronological equal-count folds with sleeve-specific and combined after-cost excess','costs_bps_per_sleeve':[25,50,100],'incomplete_months_excluded':True,'no_weight_or_parameter_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'window':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':len(idx)},'tests':tests,'decision':'P46_P36_FOLD_CONTRIBUTIONS_PERSIST' if supported else 'P46_P36_FOLD_CONTRIBUTIONS_UNEVEN'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_fold_contribution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'test50':tests['50']},sort_keys=True))
if __name__=='__main__': main()
