from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46


def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1)


def rolling(candidate, benchmark, window):
    vals=np.asarray([cagr(candidate.iloc[i-window:i])-cagr(benchmark.iloc[i-window:i]) for i in range(window,len(candidate)+1)])
    return {'windows':len(vals),'positive_fraction':float((vals>0).mean()),'median_excess_cagr':float(np.median(vals)),'p10_excess_cagr':float(np.quantile(vals,.1)),'p90_excess_cagr':float(np.quantile(vals,.9))}


def bootstrap(candidate, benchmark, reps=5000, block=12):
    x=(candidate-benchmark).dropna().to_numpy(); n=len(x); rng=np.random.default_rng(20260909); vals=[]
    for _ in range(reps):
        chunks=[]
        while sum(len(z) for z in chunks)<n:
            s=int(rng.integers(0,max(1,n-block+1))); chunks.append(x[s:s+block])
        vals.append(float(np.concatenate(chunks)[:n].mean()*12))
    a=np.asarray(vals)
    return {'annualized_mean_excess':float(x.mean()*12),'bootstrap_95pct':[float(np.quantile(a,.025)),float(np.quantile(a,.975))],'p_excess_le_zero':float((a<=0).mean()),'block_months':block,'replicates':reps}


def main():
    close=base.load(p46.SYMBOLS); frame=p46.returns(close,p46.FACTORS); out_tests={}
    for bps in (25,50,100):
        candidate=frame.gross-frame.turnover*bps/10000; ew=frame.ew
        controls={'matched_equal_weight':ew}
        for sym in ('SPY','QQQ'):
            controls[sym]=close[sym].resample('ME').last().pct_change().reindex(frame.index)
        out_tests[str(bps)]={name:{'rolling36':rolling(candidate,bm,36),'rolling60':rolling(candidate,bm,60),'bootstrap':bootstrap(candidate,bm)} for name,bm in controls.items()}
    p25=out_tests['25']['matched_equal_weight']; p50=out_tests['50']['matched_equal_weight']; q50=out_tests['50']['QQQ']
    supported=p25['rolling60']['positive_fraction']>=.6 and p25['bootstrap']['p_excess_le_zero']<=.2 and p50['bootstrap']['annualized_mean_excess']>0
    opportunity_caution=q50['bootstrap']['annualized_mean_excess']<=0
    decision='P46_SERIAL_MATCHED_ALPHA_SUPPORTED_WITH_QQQ_OPPORTUNITY_COST_CAUTION' if supported and opportunity_caution else ('P46_SERIAL_PERSISTENCE_SUPPORTED' if supported else 'P46_SERIAL_PERSISTENCE_NOT_SUPPORTED')
    out={'schema':'research.p46_serial_persistence_r2','parent':'P46','scientific_contract':{'economics':'unchanged four-factor crossasset top-2 monthly composite','costs_bps':[25,50,100],'rolling_windows_months':[36,60],'bootstrap':'12m moving block 5000 reps deterministic seed','comparators':['same-universe equal weight','SPY','QQQ'],'no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'window':{'start':str(frame.index.min().date()),'end':str(frame.index.max().date()),'months':len(frame)},'tests':out_tests,'decision':decision}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_serial_persistence_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'25_matched':p25,'50_matched':p50,'50_QQQ':q50,'window':out['window']},sort_keys=True))

if __name__=='__main__': main()
