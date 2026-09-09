from __future__ import annotations
import json
from pathlib import Path
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
    for label,ix in [('full',idx),('2022_forward',idx[idx>=pd.Timestamp('2022-01-01')])]:
        tests[label]={}
        for bp in (25,50,100):
            p46net=a.loc[ix].gross-a.loc[ix].turnover*bp/10000; p36net=b.loc[ix].gross-b.loc[ix].turnover*bp/10000
            candidate=.5*p46net+.5*p36net; matched=.5*a.loc[ix].ew+.5*b.loc[ix].matched; active=candidate-matched
            strongest=active.nlargest(5).index; keep=~candidate.index.isin(strongest)
            tests[label][str(bp)]={'full_excess_cagr':cagr(candidate)-cagr(matched),'top5_relative_months':[str(x.date()) for x in strongest],'top5_relative_sum':float(active.loc[strongest].sum()),'residual_excess_cagr':cagr(candidate[keep])-cagr(matched[keep]),'residual_months':int(keep.sum())}
    supported=tests['full']['25']['residual_excess_cagr']>0 and tests['full']['50']['residual_excess_cagr']>0 and tests['2022_forward']['25']['residual_excess_cagr']>0 and tests['2022_forward']['50']['residual_excess_cagr']>0
    out={'schema':'research.p46_p36_combined_concentration_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'research-only fixed 50% P46 + 50% P36','matched_control':'50% P46 same-universe equal weight + 50% static SMH/QQQ 50/50','costs_bps_applied_per_sleeve':[25,50,100],'falsification':'remove five strongest candidate-minus-matched months','windows':['full','2022-forward'],'incomplete_months_excluded':True,'no_weight_or_parameter_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'window':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':len(idx)},'tests':tests,'decision':'P46_P36_COMBINED_ALPHA_SURVIVES_TOP5_REMOVAL' if supported else 'P46_P36_COMBINED_ALPHA_CONCENTRATED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_combined_concentration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'tests':tests},sort_keys=True))
if __name__=='__main__': main()
