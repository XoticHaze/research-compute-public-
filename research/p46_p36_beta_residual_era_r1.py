from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
import p46_p36_combined_alpha_r1 as combo
import p46_p36_beta_residual_r1 as beta


def cagr(x):
    x=pd.Series(x,dtype=float).dropna(); return float((1+x).prod()**(12/len(x))-1)

def main():
    syms=tuple(dict.fromkeys((*p46.SYMBOLS,'SMH'))); close=base.load(syms)
    ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]
    a=p46.returns(close,p46.FACTORS); b=combo.p36_frame(close); idx=a.index.intersection(b.index); a=a.loc[idx]; b=b.loc[idx]
    monthly=close.resample('ME').last(); q=monthly['QQQ'].pct_change().reindex(idx); s=monthly['SPY'].pct_change().reindex(idx)
    bp=50; cand=.5*(a.gross-a.turnover*bp/10000)+.5*(b.gross-b.turnover*bp/10000); matched=.5*a.ew+.5*b.matched; active=cand-matched
    bounds=[('2006_2011','2006-10-31','2012-01-01'),('2012_2016','2012-01-01','2017-01-01'),('2017_2021','2017-01-01','2022-01-01'),('2022_forward','2022-01-01','2100-01-01')]
    tests={}
    for name,lo,hi in bounds:
        ix=idx[(idx>=pd.Timestamp(lo))&(idx<pd.Timestamp(hi))]
        y=active.loc[ix]; X=np.column_stack([q.loc[ix],s.loc[ix]]); r=beta.fit(y,X); r['bootstrap']=beta.boot(y,X,reps=4000,block=min(12,max(3,len(ix)//3)),seed=20260909+len(ix)); r['months']=len(ix); r['active_cagr']=cagr(y); r['candidate_cagr']=cagr(cand.loc[ix]); r['matched_cagr']=cagr(matched.loc[ix]); r['qqq_cagr']=cagr(q.loc[ix]); r['raw_excess_vs_qqq_cagr']=r['candidate_cagr']-r['qqq_cagr']; tests[name]=r
    pos=sum(v['annualized_intercept']>0 for v in tests.values()); ci=sum(v['bootstrap']['bootstrap_95pct'][0]>0 for v in tests.values())
    state='BETA_RESIDUAL_NONOVERLAP_ERA_SUPPORT' if pos>=3 and ci>=2 and tests['2022_forward']['annualized_intercept']>0 else 'BETA_RESIDUAL_NONOVERLAP_ERA_MIXED'
    out={'schema':'research.p46_p36_beta_residual_era_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'fixed 50% P46 + 50% P36','active_return':'candidate minus exact matched blend','factor_controls':['QQQ','SPY'],'cost_bps':50,'eras':['2006-2011','2012-2016','2017-2021','2022-forward'],'regression':'monthly OLS active return on QQQ and SPY with intercept; moving-block bootstrap within each non-overlap era','no_parameter_or_weight_tuning':True,'also_reports_raw_QQQ_opportunity_cost':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'positive_intercept_eras':pos,'positive_95pct_lower_bound_eras':ci,'decision':state}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_beta_residual_era_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
