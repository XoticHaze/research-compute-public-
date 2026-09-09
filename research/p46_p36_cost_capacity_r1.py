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

def test(a,b,ix,bps):
    cand=.5*(a.loc[ix].gross-a.loc[ix].turnover*bps/10000)+.5*(b.loc[ix].gross-b.loc[ix].turnover*bps/10000); matched=.5*a.loc[ix].ew+.5*b.loc[ix].matched
    return cagr(cand)-cagr(matched)

def main():
    syms=tuple(dict.fromkeys((*p46.SYMBOLS,'SMH'))); close=base.load(syms)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<current_month_start]
    a=p46.returns(close,p46.FACTORS); b=combo.p36_frame(close); idx=a.index.intersection(b.index); a=a.loc[idx]; b=b.loc[idx]
    tests={}
    for label,ix in [('full',idx),('2022_forward',idx[idx>=pd.Timestamp('2022-01-01')])]:
        grid={str(bp):test(a,b,ix,bp) for bp in range(0,501,25)}
        positive=[bp for bp in range(0,501,25) if grid[str(bp)]>0]
        approx=max(positive) if positive else None
        tests[label]={'excess_cagr_by_bps':grid,'last_positive_grid_bps':approx,'mean_p46_turnover':float(a.loc[ix].turnover.mean()),'mean_p36_turnover':float(b.loc[ix].turnover.mean()),'mean_blend_turnover_proxy':float((.5*a.loc[ix].turnover+.5*b.loc[ix].turnover).mean())}
    supported=(tests['full']['last_positive_grid_bps'] or 0)>=100 and (tests['2022_forward']['last_positive_grid_bps'] or 0)>=100
    out={'schema':'research.p46_p36_cost_capacity_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'research-only fixed 50% P46 + 50% P36','matched_control':'exact blended matched control','cost_grid_bps_per_sleeve':'0..500 step 25','purpose':'estimate after-cost survival boundary, not optimize cost or weights','windows':['full','2022-forward'],'incomplete_months_excluded':True,'no_weight_or_parameter_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'window':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':len(idx)},'tests':tests,'decision':'P46_P36_COST_CAPACITY_STRONG' if supported else 'P46_P36_COST_CAPACITY_THIN'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_cost_capacity_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'tests':tests},sort_keys=True))
if __name__=='__main__': main()
