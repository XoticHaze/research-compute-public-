from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
import p46_p36_combined_alpha_r1 as combo

def cagr(r):
    r=np.asarray(r,float); return float(np.prod(1+r)**(12/len(r))-1)

def main():
    syms=tuple(dict.fromkeys((*p46.SYMBOLS,'SMH'))); close=base.load(syms)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<current_month_start]
    a=p46.returns(close,p46.FACTORS); b=combo.p36_frame(close); idx=a.index.intersection(b.index); a=a.loc[idx]; b=b.loc[idx]
    monthly=close.resample('ME').last(); rets=monthly.pct_change().reindex(idx); p46_syms=list(p46.SYMBOLS); p36_syms=['SMH','QQQ']; matched=.5*a.ew+.5*b.matched
    tests={}
    for bp in (25,50,100):
        actual=.5*(a.gross-a.turnover*bp/10000)+.5*(b.gross-b.turnover*bp/10000); actual_excess=cagr(actual)-cagr(matched)
        rng=np.random.default_rng(46362028+bp); null=[]
        for _ in range(2000):
            prev46={s:0. for s in p46_syms}; prev36={s:0. for s in p36_syms}; path=[]
            for dt in idx:
                chosen46=set(rng.choice(p46_syms,size=2,replace=False).tolist()); pick36=str(rng.choice(p36_syms)); w46={s:(.5 if s in chosen46 else 0.) for s in p46_syms}; w36={s:(1. if s==pick36 else 0.) for s in p36_syms}
                t46=.5*sum(abs(w46[s]-prev46[s]) for s in p46_syms); t36=.5*sum(abs(w36[s]-prev36[s]) for s in p36_syms)
                g46=sum(w46[s]*float(rets.at[dt,s]) for s in p46_syms); g36=sum(w36[s]*float(rets.at[dt,s]) for s in p36_syms)
                path.append(.5*(g46-t46*bp/10000)+.5*(g36-t36*bp/10000)); prev46=w46; prev36=w36
            null.append(cagr(path)-cagr(matched))
        arr=np.asarray(null); tests[str(bp)]={'actual_excess_cagr':actual_excess,'null_mean_excess_cagr':float(arr.mean()),'null_95pct':[float(np.quantile(arr,.025)),float(np.quantile(arr,.975))],'actual_percentile':float((arr<actual_excess).mean()),'p_null_ge_actual':float((arr>=actual_excess).mean()),'replicates':len(arr)}
    supported=tests['50']['actual_percentile']>=.99 and tests['50']['p_null_ge_actual']<=.01
    out={'schema':'research.p46_p36_random_selection_null_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'fixed 50% P46 + 50% P36 research combination','matched_control':'exact blended matched control','null':'same universes/monthly cadence/cost accounting but random top-2-of-5 P46 and random 1-of-2 P36 selections each month','replicates':2000,'deterministic_seed':True,'costs_bps_per_sleeve':[25,50,100],'incomplete_months_excluded':True,'no_parameter_or_weight_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'window':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':len(idx)},'tests':tests,'decision':'P46_P36_BEATS_RANDOM_SELECTION_NULL' if supported else 'P46_P36_NOT_DISTINCT_FROM_RANDOM_SELECTION_NULL'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_random_selection_null_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'tests':tests},sort_keys=True))
if __name__=='__main__': main()
