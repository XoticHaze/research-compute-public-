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

def rolling(candidate, matched, n):
    vals=np.asarray([cagr(candidate.iloc[i-n:i])-cagr(matched.iloc[i-n:i]) for i in range(n,len(candidate)+1)])
    return {'windows':len(vals),'positive_fraction':float((vals>0).mean()),'median_excess_cagr':float(np.median(vals)),'p10_excess_cagr':float(np.quantile(vals,.1)),'p90_excess_cagr':float(np.quantile(vals,.9))}

def bootstrap(active,reps=5000,block=12):
    x=pd.Series(active,dtype=float).dropna().to_numpy(); n=len(x); rng=np.random.default_rng(46362026); vals=[]
    for _ in range(reps):
        sample=[]
        while len(sample)<n:
            s=int(rng.integers(0,max(1,n-block+1))); sample.extend(x[s:s+block])
        vals.append(float(np.mean(sample[:n])*12))
    a=np.asarray(vals); return {'annualized_mean_excess':float(np.mean(x)*12),'bootstrap_95pct':[float(np.quantile(a,.025)),float(np.quantile(a,.975))],'p_excess_le_zero':float((a<=0).mean()),'block_months':block,'replicates':reps}

def main():
    syms=tuple(dict.fromkeys((*p46.SYMBOLS,'SMH'))); close=base.load(syms)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<current_month_start]
    a=p46.returns(close,p46.FACTORS); b=combo.p36_frame(close); idx=a.index.intersection(b.index); a=a.loc[idx]; b=b.loc[idx]
    q=close['QQQ'].resample('ME').last().pct_change().reindex(idx); s=close['SPY'].resample('ME').last().pct_change().reindex(idx)
    tests={}
    for bp in (25,50,100):
        candidate=.5*(a.gross-a.turnover*bp/10000)+.5*(b.gross-b.turnover*bp/10000); matched=.5*a.ew+.5*b.matched
        controls={'blended_matched':matched,'QQQ':q,'SPY':s}; tests[str(bp)]={}
        for name,control in controls.items():
            tests[str(bp)][name]={'rolling36':rolling(candidate,control,36),'rolling60':rolling(candidate,control,60),'bootstrap':bootstrap(candidate-control)}
    p25=tests['25']['blended_matched']; p50=tests['50']['blended_matched']; supported=p25['rolling60']['positive_fraction']>=.6 and p25['bootstrap']['p_excess_le_zero']<=.1 and p50['bootstrap']['p_excess_le_zero']<=.2
    out={'schema':'research.p46_p36_combined_serial_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'research-only fixed 50% P46 + 50% P36','matched_control':'50% P46 same-universe equal weight + 50% static SMH/QQQ 50/50','opportunity_controls':['QQQ','SPY'],'costs_bps_applied_per_sleeve':[25,50,100],'rolling_windows_months':[36,60],'bootstrap':'12m moving block 5000 reps deterministic seed','incomplete_months_excluded':True,'no_weight_or_parameter_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'window':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':len(idx)},'tests':tests,'decision':'P46_P36_COMBINED_SERIAL_PERSISTENCE_SUPPORTED' if supported else 'P46_P36_COMBINED_SERIAL_PERSISTENCE_NOT_SUPPORTED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_combined_serial_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'25_matched':p25,'50_matched':p50,'25_QQQ':tests['25']['QQQ'],'25_SPY':tests['25']['SPY']},sort_keys=True))
if __name__=='__main__': main()
