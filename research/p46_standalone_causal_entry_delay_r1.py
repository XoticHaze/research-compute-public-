from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46

BPS=(25,50,100)
DELAYS=(1,3,5)

def cagr(x):
    x=pd.Series(x,dtype=float).dropna()
    return float((1+x).prod()**(12/len(x))-1) if len(x) else float('nan')

def main():
    syms=tuple(p46.SYMBOLS)
    close=base.load(syms)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp()
    close=close.loc[close.index<current_month_start]
    panel,monthly=p46.feature_panel(close[list(syms)],p46.FACTORS)
    signals={}
    for dt in sorted(panel.month.unique()):
        block=panel[panel.month==dt].sort_values(['score','symbol'],ascending=[False,True])
        if len(block)!=len(syms):
            continue
        chosen=set(block.head(2).symbol.tolist())
        signals[pd.Timestamp(dt)]={s:(0.5 if s in chosen else 0.0) for s in syms}
    labels=sorted(signals)
    daily=close.index
    tests={}
    for delay in DELAYS:
        tests[str(delay)]={}
        for bp in BPS:
            prev={s:0.0 for s in syms}
            rec=[]
            for i in range(len(labels)-1):
                dt,nxt=labels[i],labels[i+1]
                left=daily[daily<=dt]
                right=daily[daily<=nxt]
                if not len(left) or not len(right):
                    continue
                a=int(daily.get_loc(left[-1]))+delay
                z=int(daily.get_loc(right[-1]))+delay
                if a>=len(daily) or z>=len(daily) or z<=a:
                    continue
                r=close.loc[daily[z],list(syms)]/close.loc[daily[a],list(syms)]-1.0
                if r.isna().any():
                    continue
                w=signals[dt]
                turn=0.5*sum(abs(w[s]-prev[s]) for s in syms)
                cand=sum(w[s]*float(r[s]) for s in syms)-turn*bp/10000.0
                matched=float(r.mean())
                rec.append((daily[z],cand,matched,turn))
                prev=w
            f=pd.DataFrame(rec,columns=['date','candidate','matched','turnover']).set_index('date')
            folds=[]
            for n,ids in enumerate(np.array_split(np.arange(len(f)),5),1):
                q=f.iloc[ids]
                ce=cagr(q.candidate); be=cagr(q.matched)
                folds.append({'fold':n,'candidate_cagr':ce,'matched_cagr':be,'excess_cagr':ce-be})
            tests[str(delay)][str(bp)]={
                'months':int(len(f)),
                'start':str(f.index.min().date()) if len(f) else None,
                'end':str(f.index.max().date()) if len(f) else None,
                'candidate_cagr':cagr(f.candidate),
                'matched_cagr':cagr(f.matched),
                'excess_cagr':cagr(f.candidate)-cagr(f.matched),
                'positive_folds':int(sum(x['excess_cagr']>0 for x in folds)),
                'annual_turnover':float(f.turnover.mean()*12) if len(f) else None,
                'folds':folds,
            }
    p1=tests['1']['50']; p3=tests['3']['50']; p5=tests['5']['50']
    if p1['excess_cagr']>0 and p1['positive_folds']>=3 and p3['excess_cagr']>0:
        decision='P46_STANDALONE_CAUSAL_EXECUTION_DELAY_SUPPORTED'
    elif p1['excess_cagr']>0 and p1['positive_folds']>=3:
        decision='P46_STANDALONE_CAUSAL_EXECUTION_DELAY_PARTIAL'
    else:
        decision='P46_STANDALONE_CAUSAL_EXECUTION_DELAY_NOT_SUPPORTED'
    out={
        'schema':'research.p46_standalone_causal_entry_delay_r1',
        'parent':'P46',
        'scientific_contract':{
            'candidate':'fixed four-factor top-2 monthly cross-asset selector',
            'representation':list(syms),
            'entry_and_rebalance_delays_trading_days':list(DELAYS),
            'costs_bps':list(BPS),
            'matched_control':'same-universe equal weight over exact shifted holding intervals',
            'purpose':'claim-relevant implementation timing test; unlike a many-month stale-signal placebo, this tests whether an executable delay after signal formation preserves the edge',
            'no_parameter_or_weight_tuning':True,
        },
        'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},
        'tests':tests,
        'decision':decision,
        'interpretation_rule':'A failure here is scientific evidence only about execution-delay robustness of the frozen P46 implementation. It does not retroactively convert a stale-signal placebo into a valid rejection gate for a slow-moving monthly ranking signal.'
    }
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p46_standalone_causal_entry_delay_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps({'decision':decision,'d1_50':p1,'d3_50':p3,'d5_50':p5},sort_keys=True))

if __name__=='__main__':
    main()
