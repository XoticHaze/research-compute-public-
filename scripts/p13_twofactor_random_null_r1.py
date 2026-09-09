from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import p13_semiconductor_stock_specific_residual as p13
import p13_twofactor_residual_r1 as tf

REPS=3000
TOP_N=p13.TOP_N
COST_BPS=50


def cagr(x):
    x=np.asarray(x,float)
    return float(np.prod(1+x)**(12/len(x))-1)


def build_periods():
    close, volume=p13.download()
    positions=p13.month_end_indices(close.index)
    rows=[]
    for j in range(len(positions)-1):
        sig,nxt=positions[j],positions[j+1]
        entry,exit_=sig+1,nxt+1
        if sig<p13.LOOKBACK or entry>=len(close) or exit_>=len(close) or close.index[entry] < pd.Timestamp('2019-01-01'):
            continue
        two={}; one={}; raw={}
        for name in p13.UNIVERSE:
            now,then=close.iloc[sig][name],close.iloc[sig-p13.LOOKBACK][name]
            if np.isfinite(now) and np.isfinite(then) and then>0: raw[name]=float(now/then-1)
            s1=p13.stock_specific_residual_score(close,name,sig); s2=tf.score_twofactor(close,name,sig)
            if np.isfinite(s1): one[name]=s1
            if np.isfinite(s2): two[name]=s2
        common=sorted(set(raw).intersection(one).intersection(two))
        if len(common)<8: continue
        chosen=sorted(common,key=lambda n:two[n],reverse=True)[:TOP_N]
        realized={n:p13.asset_return(close,n,entry,exit_) for n in common}
        if not all(np.isfinite(v) for v in realized.values()): continue
        smh=p13.asset_return(close,'SMH',entry,exit_); qqq=p13.asset_return(close,'QQQ',entry,exit_)
        if not np.isfinite(smh) or not np.isfinite(qqq): continue
        rows.append({'entry':close.index[entry],'names':common,'chosen':chosen,'realized':realized,'actual':float(np.mean([realized[n] for n in chosen])),'ew':float(np.mean(list(realized.values()))),'smh':smh,'qqq':qqq})
    return rows


def evaluate(rows,seed):
    rng=np.random.default_rng(seed); drag=COST_BPS/10000
    actual=np.array([r['actual']-drag for r in rows]); ew=np.array([r['ew'] for r in rows]); smh=np.array([r['smh'] for r in rows]); qqq=np.array([r['qqq'] for r in rows])
    null=[]
    for _ in range(REPS):
        rr=[]
        for r in rows:
            pick=rng.choice(r['names'],size=TOP_N,replace=False)
            rr.append(float(np.mean([r['realized'][n] for n in pick]))-drag)
        null.append(cagr(rr))
    n=np.asarray(null); ac=cagr(actual)
    return {'months':len(rows),'actual_cagr':ac,'equal_weight_cagr':cagr(ew),'smh_cagr':cagr(smh),'qqq_cagr':cagr(qqq),'actual_excess_vs_equal_weight':ac-cagr(ew),'actual_excess_vs_smh':ac-cagr(smh),'actual_excess_vs_qqq':ac-cagr(qqq),'null_replicates':REPS,'null_cagr_median':float(np.median(n)),'null_cagr_95pct':[float(np.quantile(n,.025)),float(np.quantile(n,.975))],'actual_percentile':float(np.mean(n<=ac)),'p_null_ge_actual':float(np.mean(n>=ac))}


def main():
    rows=build_periods(); full=rows; recent=[r for r in rows if r['entry']>=pd.Timestamp('2022-01-01')]
    tests={'full':evaluate(full,2026090913),'2022_forward':evaluate(recent,2026090914)}
    r=tests['2022_forward']; state='P13_TWOFACTOR_SELECTION_SPECIFICITY_SUPPORTED' if r['actual_excess_vs_smh']>0 and r['p_null_ge_actual']<=.05 and tests['full']['p_null_ge_actual']<=.05 else 'P13_TWOFACTOR_SELECTION_SPECIFICITY_NOT_SUPPORTED'
    out={'schema':'research.p13_twofactor_random_null_r1','parent':'P13','scientific_contract':{'candidate':'prior-only 126-session SMH+QQQ residual top-3 monthly','null':'random top-3 sampled without replacement from each month exact eligible same-name universe','cost_bps':COST_BPS,'replicates':REPS,'windows':['full','2022-forward'],'comparators':['equal-weight eligible universe','SMH','QQQ'],'known_current-name_survivorship_risk_preserved':True,'no_parameter_search':True},'tests':tests,'decision':state}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p13_twofactor_random_null_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
