from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

REPS=3000; BP=50

def cagr(x):
    x=np.asarray(x,float); return float(np.prod(1+x)**(12/len(x))-1)

def main():
    close=base.load(p46.SYMBOLS); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]
    panel,monthly=p46.feature_panel(close[list(p46.SYMBOLS)],p46.FACTORS); months=sorted(panel.month.unique()); prev={s:0. for s in p46.SYMBOLS}; rows=[]
    for dt in months:
        block=panel[panel.month==dt].sort_values(['score','symbol'],ascending=[False,True])
        if len(block)!=len(p46.SYMBOLS): continue
        loc=monthly.index.get_loc(dt)
        if not isinstance(loc,(int,np.integer)) or loc+1>=len(monthly): continue
        nxt=monthly.index[loc+1]; r=monthly.loc[nxt,list(p46.SYMBOLS)]/monthly.loc[dt,list(p46.SYMBOLS)]-1
        if r.isna().any(): continue
        chosen=block.head(2).symbol.tolist(); w={s:(.5 if s in chosen else 0.) for s in p46.SYMBOLS}; turnover=.5*sum(abs(w[s]-prev[s]) for s in p46.SYMBOLS)
        actual=sum(w[s]*float(r[s]) for s in p46.SYMBOLS)-turnover*BP/10000; rows.append({'date':pd.Timestamp(nxt),'actual':actual,'ew':float(r.mean()),'returns':{s:float(r[s]) for s in p46.SYMBOLS}}); prev=w
    def evaluate(rr,seed):
        rng=np.random.default_rng(seed); actual=[x['actual'] for x in rr]; ew=[x['ew'] for x in rr]; null=[]
        for _ in range(REPS):
            pp={s:0. for s in p46.SYMBOLS}; out=[]
            for x in rr:
                pick=set(rng.choice(p46.SYMBOLS,size=2,replace=False)); w={s:(.5 if s in pick else 0.) for s in p46.SYMBOLS}; turn=.5*sum(abs(w[s]-pp[s]) for s in p46.SYMBOLS); out.append(sum(w[s]*x['returns'][s] for s in p46.SYMBOLS)-turn*BP/10000); pp=w
            null.append(cagr(out))
        n=np.asarray(null); ac=cagr(actual); return {'months':len(rr),'actual_cagr':ac,'matched_equal_weight_cagr':cagr(ew),'actual_excess_vs_equal_weight':ac-cagr(ew),'null_replicates':REPS,'null_cagr_median':float(np.median(n)),'null_cagr_95pct':[float(np.quantile(n,.025)),float(np.quantile(n,.975))],'actual_percentile':float(np.mean(n<=ac)),'p_null_ge_actual':float(np.mean(n>=ac))}
    recent=[x for x in rows if x['date']>=pd.Timestamp('2022-01-01')]; tests={'full':evaluate(rows,2026090915),'2022_forward':evaluate(recent,2026090916)}; state='P46_STANDALONE_SELECTION_SPECIFICITY_SUPPORTED' if tests['full']['p_null_ge_actual']<=.05 and tests['2022_forward']['p_null_ge_actual']<=.1 and tests['2022_forward']['actual_excess_vs_equal_weight']>0 else 'P46_STANDALONE_SELECTION_SPECIFICITY_NOT_SUPPORTED'
    out={'schema':'research.p46_standalone_random_selection_null_r1','parent':'P46','scientific_contract':{'candidate':'fixed four-factor top-2 cross-asset selector','null':'random top-2 monthly selector from same five-asset universe with realized turnover charged identically','cost_bps':BP,'replicates':REPS,'windows':['full','2022-forward'],'matched_control':'same-universe equal weight','no_parameter_or_weight_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_standalone_random_selection_null_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
