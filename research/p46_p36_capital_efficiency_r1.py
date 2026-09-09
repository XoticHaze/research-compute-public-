from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
import p46_p36_combined_alpha_r1 as combo

def metrics(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); dd=eq/eq.cummax()-1
    cagr=float(eq.iloc[-1]**(12/len(r))-1); vol=float(r.std(ddof=0)*math.sqrt(12)); sharpe=float(r.mean()/r.std(ddof=0)*math.sqrt(12)) if r.std(ddof=0)>0 else 0.0
    mdd=float(dd.min()); calmar=float(cagr/abs(mdd)) if mdd<0 else None
    return {'cagr':cagr,'vol':vol,'sharpe_rf0':sharpe,'max_drawdown':mdd,'calmar':calmar,'months':len(r)}

def main():
    syms=tuple(dict.fromkeys((*p46.SYMBOLS,'SMH'))); close=base.load(syms)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<current_month_start]
    a=p46.returns(close,p46.FACTORS); b=combo.p36_frame(close); idx=a.index.intersection(b.index); a=a.loc[idx]; b=b.loc[idx]
    monthly=close.resample('ME').last(); q=monthly['QQQ'].pct_change().reindex(idx); s=monthly['SPY'].pct_change().reindex(idx)
    tests={}
    for label,ix in [('full',idx),('2022_forward',idx[idx>=pd.Timestamp('2022-01-01')])]:
        tests[label]={}
        for bp in (25,50,100):
            p46net=a.loc[ix].gross-a.loc[ix].turnover*bp/10000; p36net=b.loc[ix].gross-b.loc[ix].turnover*bp/10000
            candidate=.5*p46net+.5*p36net; matched=.5*a.loc[ix].ew+.5*b.loc[ix].matched; qq=q.loc[ix]; sp=s.loc[ix]
            active=candidate-matched
            q_up=qq>0; q_down=~q_up
            tests[label][str(bp)]={
                'candidate':metrics(candidate),'matched':metrics(matched),'QQQ':metrics(qq),'SPY':metrics(sp),
                'excess_cagr_vs_matched':metrics(candidate)['cagr']-metrics(matched)['cagr'],
                'excess_cagr_vs_QQQ':metrics(candidate)['cagr']-metrics(qq)['cagr'],
                'excess_cagr_vs_SPY':metrics(candidate)['cagr']-metrics(sp)['cagr'],
                'mean_active_when_QQQ_up':float(active[q_up].mean()),'mean_active_when_QQQ_down':float(active[q_down].mean()),
                'mean_monthly_turnover':float((.5*a.loc[ix].turnover+.5*b.loc[ix].turnover).mean()),
                'capital_usage_fraction':1.0,'leverage':1.0,
            }
    f=tests['full']['50']; supported=f['excess_cagr_vs_matched']>0 and f['candidate']['sharpe_rf0']>=f['matched']['sharpe_rf0'] and f['candidate']['calmar']>=f['matched']['calmar']
    out={'schema':'research.p46_p36_capital_efficiency_r1','parents':['P46','P36'],'scientific_contract':{'candidate':'research-only fixed 50% P46 + 50% P36','matched_control':'50% P46 same-universe equal weight + 50% static SMH/QQQ 50/50','opportunity_controls':['QQQ','SPY'],'costs_bps_applied_per_sleeve':[25,50,100],'windows':['full','2022-forward'],'capital_usage_fraction':1.0,'leverage':1.0,'incomplete_months_excluded':True,'no_weight_or_parameter_tuning':True,'no_portfolio_authority':True},'source':{'provider':'Yahoo Finance via yfinance','normalized_complete_month_price_panel_sha256':base.source_hash(close)},'window':{'start':str(idx.min().date()),'end':str(idx.max().date()),'months':len(idx)},'tests':tests,'decision':'P46_P36_CAPITAL_EFFICIENCY_SUPPORTED' if supported else 'P46_P36_CAPITAL_EFFICIENCY_MIXED'}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_capital_efficiency_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':out['decision'],'window':out['window'],'full50':f,'recent50':tests['2022_forward']['50']},sort_keys=True))
if __name__=='__main__': main()
