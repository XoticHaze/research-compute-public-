from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

P46_SYMS=tuple(p46.SYMBOLS)

def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)

def p46_signals(close):
    panel,monthly=p46.feature_panel(close[P46_SYMS],p46.FACTORS); out={}
    for dt in sorted(panel.month.unique()):
        block=panel[panel.month==dt].sort_values(['score','symbol'],ascending=[False,True]);
        if len(block)!=len(P46_SYMS): continue
        chosen=set(block.head(2).symbol.tolist()); out[pd.Timestamp(dt)]={s:(.5 if s in chosen else 0.) for s in P46_SYMS}
    return monthly[P46_SYMS],out

def p36_signals(close):
    monthly=close[['SMH','QQQ']].resample('ME').last(); mom=monthly.pct_change(6); out={}
    for dt in monthly.index:
        if mom.loc[dt].isna().any(): continue
        pick='SMH' if mom.at[dt,'SMH']>mom.at[dt,'QQQ'] else 'QQQ'; out[dt]={'SMH':1. if pick=='SMH' else 0.,'QQQ':1. if pick=='QQQ' else 0.}
    return monthly,out

def evaluate(close,lag,bps):
    m46,s46=p46_signals(close); m36,s36=p36_signals(close); months=m46.index.intersection(m36.index); rec=[]; prev46={s:0. for s in P46_SYMS}; prev36={'SMH':0.,'QQQ':0.}
    for i in range(1+lag,len(months)):
        realized_month=months[i]; signal_month=months[i-1-lag]
        if signal_month not in s46 or signal_month not in s36: continue
        prev_month=months[i-1]; r46=m46.loc[realized_month]/m46.loc[prev_month]-1; r36=m36.loc[realized_month]/m36.loc[prev_month]-1
        if r46.isna().any() or r36.isna().any(): continue
        w46=s46[signal_month]; w36=s36[signal_month]; t46=.5*sum(abs(w46[s]-prev46[s]) for s in P46_SYMS); t36=.5*sum(abs(w36[s]-prev36[s]) for s in ('SMH','QQQ'))
        g46=sum(w46[s]*float(r46[s]) for s in P46_SYMS); g36=sum(w36[s]*float(r36[s]) for s in ('SMH','QQQ'))
        cand=.5*(g46-t46*bps/10000)+.5*(g36-t36*bps/10000); matched=.5*float(r46.mean())+.5*.5*float(r36['SMH']+r36['QQQ'])
        rec.append((realized_month,cand,matched)); prev46=w46; prev36=w36
    f=pd.DataFrame(rec,columns=['date','candidate','matched']).set_index('date'); return {'months':len(f),'start':str(f.index.min().date()),'end':str(f.index.max().date()),'excess_cagr':cagr(f.candidate)-cagr(f.matched)}

def main():
    syms=tuple(dict.fromkeys((*P46_SYMS,'SMH'))); close=base.load(syms); current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<current_month_start]
    tests={str(lag):{str(bp):evaluate(close,lag,bp) for bp in (25,50)} for lag in range(0,25)}
    actual50=tests['0']['50']['excess_cagr']; placebo50=np.asarray([tests[str(k)]['50']['excess_cagr'] for k in range(1,25)]); percentile=float((placebo50<actual50).mean())
    supported=percentile>=.9 and actual50>0
    out={'schema':'research.p46_p36_signal_lag_placebo_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'fixed 50% P46 + 50% P36 research combination','matched_control':'exact blended matched control','test':'apply the same historical signals with 0 through 24 additional completed-month lags; lag0 is frozen mechanism and lags1-24 are timing placebos','costs_bps_per_sleeve':[25,50],'incomplete_months_excluded':True,'no_parameter_or_weight_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'lag0_50bps_placebo_percentile':percentile,'decision':'P46_P36_TIMING_SPECIFICITY_SUPPORTED' if supported else 'P46_P36_TIMING_SPECIFICITY_WEAK'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_signal_lag_placebo_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'lag0_50':actual50,'placebo_percentile':percentile,'lag_excess_50':{k:v['50']['excess_cagr'] for k,v in tests.items()}},sort_keys=True))
if __name__=='__main__': main()
