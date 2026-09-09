from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

BP=50; LAGS=(0,1,2,3,6,12)
def cagr(x):
    x=np.asarray(x,float); return float(np.prod(1+x)**(12/len(x))-1)
def main():
    close=base.load(p46.SYMBOLS); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]
    panel,monthly=p46.feature_panel(close[list(p46.SYMBOLS)],p46.FACTORS); months=sorted(panel.month.unique()); signals=[]
    for dt in months:
        block=panel[panel.month==dt].sort_values(['score','symbol'],ascending=[False,True])
        if len(block)==len(p46.SYMBOLS): signals.append({'date':pd.Timestamp(dt),'pick':block.head(2).symbol.tolist()})
    def eval_lag(lag,start=None):
        prev={s:0. for s in p46.SYMBOLS}; rr=[]; ew=[]; dates=[]
        for i in range(lag,len(signals)):
            sig=signals[i-lag]; dt=signals[i]['date']
            if start is not None and dt<start: continue
            loc=monthly.index.get_loc(dt)
            if not isinstance(loc,(int,np.integer)) or loc+1>=len(monthly): continue
            nxt=monthly.index[loc+1]; r=monthly.loc[nxt,list(p46.SYMBOLS)]/monthly.loc[dt,list(p46.SYMBOLS)]-1
            if r.isna().any(): continue
            pick=set(sig['pick']); w={s:(.5 if s in pick else 0.) for s in p46.SYMBOLS}; turn=.5*sum(abs(w[s]-prev[s]) for s in p46.SYMBOLS); rr.append(sum(w[s]*float(r[s]) for s in p46.SYMBOLS)-turn*BP/10000); ew.append(float(r.mean())); dates.append(str(nxt.date())); prev=w
        return {'months':len(rr),'candidate_cagr':cagr(rr),'equal_weight_cagr':cagr(ew),'excess_vs_equal_weight':cagr(rr)-cagr(ew),'first_return_month':dates[0] if dates else None,'last_return_month':dates[-1] if dates else None}
    tests={lab:{str(l):eval_lag(l,start) for l in LAGS} for lab,start in [('full',None),('2022_forward',pd.Timestamp('2022-01-01'))]}
    r=tests['2022_forward']; aligned=r['0']['excess_vs_equal_weight']; best_placebo=max(r[str(l)]['excess_vs_equal_weight'] for l in LAGS if l); decision='P46_STANDALONE_TIMING_SPECIFICITY_SUPPORTED' if aligned>0 and best_placebo<aligned*.5 else 'P46_STANDALONE_TIMING_SPECIFICITY_WEAK'
    out={'schema':'research.p46_standalone_signal_lag_placebo_r1','parent':'P46','scientific_contract':{'candidate':'fixed four-factor top-2 cross-asset selector','placebo':'apply monthly rankings delayed by 1,2,3,6,12 signal months to later returns','cost_bps':BP,'matched_control':'same-universe equal weight','no_parameter_or_weight_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'aligned_recent_excess':aligned,'best_lagged_recent_excess':best_placebo,'decision':decision}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_standalone_signal_lag_placebo_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
