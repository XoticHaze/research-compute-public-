from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46


def summarize(x):
    x=pd.Series(x,dtype=float).dropna()
    return {'months':len(x),'annualized_mean':float(x.mean()*12),'positive_month_fraction':float((x>0).mean()),'median_monthly':float(x.median()),'p10_monthly':float(x.quantile(.1)),'p90_monthly':float(x.quantile(.9))}


def bootstrap(x,reps=5000,block=6):
    x=pd.Series(x,dtype=float).dropna().to_numpy(); n=len(x); rng=np.random.default_rng(20260909); vals=[]
    for _ in range(reps):
        chunks=[]
        while sum(len(z) for z in chunks)<n:
            s=int(rng.integers(0,max(1,n-block+1))); chunks.append(x[s:s+block])
        vals.append(float(np.concatenate(chunks)[:n].mean()*12))
    a=np.asarray(vals)
    return {'annualized_mean_excess':float(x.mean()*12),'bootstrap_95pct':[float(np.quantile(a,.025)),float(np.quantile(a,.975))],'p_excess_le_zero':float((a<=0).mean()),'block_months':block,'replicates':reps}


def main():
    close=base.load(p46.SYMBOLS); frame=p46.returns(close,p46.FACTORS)
    spy_m=close['SPY'].resample('ME').last(); qqq=close['QQQ'].resample('ME').last().pct_change().reindex(frame.index)
    prior_spy6=spy_m.pct_change(6).shift(1).reindex(frame.index)
    out_tests={}
    for bps in (25,50,100):
        candidate=frame.gross-frame.turnover*bps/10000; excess=candidate-qqq
        states={'risk_on':excess[prior_spy6>0],'risk_off':excess[prior_spy6<=0]}
        out_tests[str(bps)]={'overall':{'summary':summarize(excess),'bootstrap':bootstrap(excess)},'risk_on':{'summary':summarize(states['risk_on']),'bootstrap':bootstrap(states['risk_on'])},'risk_off':{'summary':summarize(states['risk_off']),'bootstrap':bootstrap(states['risk_off'])}}
    r25=out_tests['25']; concentrated=(r25['risk_on']['summary']['annualized_mean']*r25['risk_off']['summary']['annualized_mean']<0)
    out={'schema':'research.p46_qqq_regime_attribution_r1','parent':'P46','scientific_contract':{'candidate':'unchanged P46 four-factor crossasset top-2 monthly composite','opportunity_cost':'QQQ buy-and-hold monthly return','state':'prior SPY six-month return sign, lagged one month','costs_bps':[25,50,100],'purpose':'attribute QQQ opportunity-cost deficit without changing allocation','no_parameter_tuning':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_price_panel_sha256':base.source_hash(close)},'window':{'start':str(frame.index.min().date()),'end':str(frame.index.max().date()),'months':len(frame)},'tests':out_tests,'decision':'P46_QQQ_OPPORTUNITY_COST_REGIME_CONCENTRATED' if concentrated else 'P46_QQQ_OPPORTUNITY_COST_BROAD'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_qqq_regime_attribution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'25':out_tests['25'],'50':out_tests['50']},sort_keys=True))
if __name__=='__main__': main()
