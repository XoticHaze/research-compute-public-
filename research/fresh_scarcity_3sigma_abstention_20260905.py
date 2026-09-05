from __future__ import annotations

"""Support-aware abstention discriminator after PR273 fresh scarcity rejection.

The 3-sigma support boundary is inherited from the outcome-agnostic PR23 diagnostic,
which predeclared |training-z| > 3 as the OOD triage boundary before this consumer
looks at economics. The exact PR22/PR273 19-feature Ridge, admission (>0), +1/fixed20,
two-slot mechanics and 200 bps cost remain frozen. The only new policy is to refuse a
candidate when any feature lies outside +/-3 fold-local training standard deviations.
If fewer than two support-safe candidates remain, scarce capital stays unallocated.
This exposed fresh cohort is mechanism-only; any positive result still requires a new
prospectively frozen confirmation cohort.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import research.fresh_scarcity_confirmation_20260905 as base

OUT = Path('fresh_scarcity_3sigma_abstention_20260905.json')
SUPPORT_Z = 3.0
COST = 200.0
MIN_EXECUTED = 30
MIN_COVERAGE = 0.40


def mean(xs):
    return None if not xs else float(np.mean(xs))


def spearman(a,b):
    return base.spearman(np.asarray(a,float),np.asarray(b,float))


def summarize(rows):
    if not rows:
        return {'decisions':0}
    safe=np.asarray([r['safe_top2_gross']-COST for r in rows],float)
    ew=np.asarray([r['safe_ew_gross']-COST for r in rows],float)
    smh=np.asarray([r['smh_gross']-COST for r in rows],float)
    baseline=np.asarray([r['baseline_top2_gross']-COST for r in rows],float)
    ics=[r['safe_ic'] for r in rows if r['safe_ic'] is not None]
    return {
        'decisions':len(rows),
        'mean_safe_top2_net200_bps':float(safe.mean()),
        'mean_safe_excess_vs_safe_ew_bps':float((safe-ew).mean()),
        'mean_safe_excess_vs_smh_bps':float((safe-smh).mean()),
        'mean_safe_rank_ic':mean(ics),
        'mean_exact_baseline_top2_net_same_dates_bps':float(baseline.mean()),
        'mean_safe_minus_exact_baseline_top2_bps':float((safe-baseline).mean()),
    }


def main():
    symbols=(*base.TRAIN,*base.FRESH,*base.CONTEXT)
    raw={s:base.load(s) for s in symbols}
    cutoff=min(d.iloc[-1].timestamp for d in raw.values())
    sets=[set(d.loc[d.timestamp<=cutoff,'timestamp']) for d in raw.values()]
    cal=pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(cal)<1500: raise RuntimeError(f'insufficient common calendar={len(cal)}')
    prices={s:raw[s].set_index('timestamp').price.reindex(cal) for s in raw}
    if any(v.isna().any() for v in prices.values()): raise RuntimeError('missing common-calendar price')
    data=base.engineer(prices,cal); fs=base.folds(len(cal)); tr=base.frame(base.TRAIN,data,fs,base.FULL)

    executed=[]; baseline_dates=0; skipped_support=0; fold_summaries=[]; symbol_reject={s:{'admitted':0,'support_rejected':0} for s in base.FRESH}
    for f in range(2,7):
        start,stop=fs[f-1]; train=tr[tr.signal_i<start-base.PURGE]
        model=base.fit(train,base.FULL); scaler=model.named_steps['scale']
        fold_rows=[]; fold_baseline=0; fold_skip=0
        i=start; safe_stop=stop-(base.DELAY+base.HOLD)
        while i<safe_stop:
            ei=i+base.DELAY; xi=ei+base.HOLD; allc=[]; safec=[]
            for s in base.FRESH:
                vals=data[s].loc[i,base.FULL].to_numpy(float)
                if not np.isfinite(vals).all(): continue
                score=float(model.predict(np.asarray([vals],float))[0])
                if score<=0: continue
                gross=float(prices[s].iloc[xi]/prices[s].iloc[ei]-1)*10000.0
                z=scaler.transform(np.asarray([vals],float))[0]; mz=float(np.max(np.abs(z)))
                row={'symbol':s,'score':score,'gross':gross,'max_abs_train_z':mz}
                allc.append(row); symbol_reject[s]['admitted']+=1
                if mz<=SUPPORT_Z: safec.append(row)
                else: symbol_reject[s]['support_rejected']+=1
            if len(allc)>=2:
                baseline_dates+=1; fold_baseline+=1
                allc.sort(key=lambda r:(-r['score'],r['symbol']))
                if len(safec)<2:
                    skipped_support+=1; fold_skip+=1; i+=base.HOLD; continue
                safec.sort(key=lambda r:(-r['score'],r['symbol']))
                safe_top=safec[:2]; baseline_top=allc[:2]
                fold_rows.append({
                    'fold':f,'safe_top2_gross':float(np.mean([r['gross'] for r in safe_top])),
                    'safe_ew_gross':float(np.mean([r['gross'] for r in safec])),
                    'smh_gross':float(prices['SMH'].iloc[xi]/prices['SMH'].iloc[ei]-1)*10000.0,
                    'baseline_top2_gross':float(np.mean([r['gross'] for r in baseline_top])),
                    'safe_ic':spearman([r['score'] for r in safec],[r['gross'] for r in safec]),
                    'safe_count':len(safec),'baseline_admitted_count':len(allc),
                })
            i+=base.HOLD
        executed.extend(fold_rows)
        s=summarize(fold_rows); s.update({'fold':f,'baseline_decision_dates':fold_baseline,'skipped_for_support':fold_skip,'coverage':0.0 if not fold_baseline else len(fold_rows)/fold_baseline}); fold_summaries.append(s)

    agg=summarize(executed); coverage=0.0 if not baseline_dates else len(executed)/baseline_dates
    agg.update({
        'baseline_decision_dates':baseline_dates,'skipped_for_support':skipped_support,'coverage':coverage,
        'positive_net_folds':sum((r.get('mean_safe_top2_net200_bps') or -1)>0 for r in fold_summaries),
        'safe_ew_winning_folds':sum((r.get('mean_safe_excess_vs_safe_ew_bps') or -1)>0 for r in fold_summaries),
        'smh_winning_folds':sum((r.get('mean_safe_excess_vs_smh_bps') or -1)>0 for r in fold_summaries),
        'positive_ic_folds':sum((r.get('mean_safe_rank_ic') or -1)>0 for r in fold_summaries),
        'baseline_improvement_folds':sum((r.get('mean_safe_minus_exact_baseline_top2_bps') or -1)>0 for r in fold_summaries),
    })
    enough=bool(len(executed)>=MIN_EXECUTED and coverage>=MIN_COVERAGE and sum(r['decisions']>=3 for r in fold_summaries)>=3)
    economics=bool(enough and agg['mean_safe_top2_net200_bps']>0 and agg['mean_safe_excess_vs_safe_ew_bps']>0 and agg['mean_safe_excess_vs_smh_bps']>0 and (agg['mean_safe_rank_ic'] or -1)>0 and agg['mean_safe_minus_exact_baseline_top2_bps']>0 and agg['positive_net_folds']>=3 and agg['safe_ew_winning_folds']>=3 and agg['smh_winning_folds']>=3 and agg['positive_ic_folds']>=3 and agg['baseline_improvement_folds']>=3)
    decision='SUPPORT_ABSTENTION_MECHANISM_EVIDENCE' if economics else ('INSUFFICIENT_SUPPORTED_SCARCITY_COVERAGE' if not enough else 'REJECT_3SIGMA_SUPPORT_ABSTENTION')
    out={
        'schema':'public_compute.fresh_scarcity_3sigma_abstention.v1','generated_at':datetime.now(timezone.utc).isoformat(),
        'source_parent':'public PR22 frozen PR273 confirmation capsule + PR23 outcome-agnostic support diagnostic',
        'support_rule':{'max_abs_fold_local_training_z_lte':SUPPORT_Z,'rule_frozen_before_economic_evaluation':True,'fallback':'cash/no allocation when fewer than two support-safe candidates'},
        'frozen_science':{'model':'exact 19-feature StandardScaler+Ridge(alpha=10)','admission':'predicted value > 0','slots':2,'delay':1,'hold':20,'cost_bps':200},
        'aggregate':agg,'folds':fold_summaries,'per_symbol_support_rejection':symbol_reject,
        'mechanism_gate':{'min_executed_decisions':MIN_EXECUTED,'min_coverage':MIN_COVERAGE,'decision':decision},
        'interpretation':'mechanism-only on an exposed fresh cohort; any positive result requires a new prospectively frozen confirmation and cannot create scarcity/trading authority',
        'research_only':True,'promotion_authority':False,'runtime_mutation':False,'live_trading_change':False
    }
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print('FRESH_SCARCITY_3SIGMA_ABSTENTION='+json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
