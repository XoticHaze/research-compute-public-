from __future__ import annotations

"""Fresh-cohort support diagnostic for the rejected PR273 scarcity confirmation.

Uses only the already-public PR22 execution capsule. The exact 19-feature Ridge is fit
on the original seven-symbol training domain. The fresh eight-name cohort is measured
against fold-local training support on the same 20-session decision cadence. Outcomes
are not used to choose groups, thresholds or a rescue rule.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import research.fresh_scarcity_confirmation_20260905 as base

OUT = Path('fresh_scarcity_support_diagnostic_20260905.json')
GROUPS = {
    'own_state': ['mom5','mom20','mom60','mom100','mom20_z252','mom20_accel5','vol20','vol20_z252','distance_high60'],
    'relative_state': ['rs_smh20','rs_smh60','rs_qqq20','rs_qqq60'],
    'market_context': ['smh_mom20','smh_mom100','qqq_mom20','qqq_mom100'],
    'breadth_cross_section': ['survivor_breadth_positive20','survivor_cross_section_mom20_pct'],
}


def main():
    symbols=(*base.TRAIN,*base.FRESH,*base.CONTEXT)
    raw={s:base.load(s) for s in symbols}
    cutoff=min(d.iloc[-1].timestamp for d in raw.values())
    sets=[set(d.loc[d.timestamp<=cutoff,'timestamp']) for d in raw.values()]
    cal=pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(cal)<1500: raise RuntimeError(f'insufficient common calendar {len(cal)}')
    prices={s:raw[s].set_index('timestamp').price.reindex(cal) for s in raw}
    if any(v.isna().any() for v in prices.values()): raise RuntimeError('missing common-calendar price')
    data=base.engineer(prices,cal); fs=base.folds(len(cal)); tr=base.frame(base.TRAIN,data,fs,base.FULL)

    rows=[]; fold_rows=[]
    per_symbol={s:{'finite':0,'admitted':0,'outside3':0,'max_abs_z':[]} for s in base.FRESH}
    for f in range(2,7):
        start,stop=fs[f-1]; train=tr[tr.signal_i<start-base.PURGE]
        model=base.fit(train,base.FULL); scaler=model.named_steps['scale']; ridge=model.named_steps['ridge']
        z_all=[]; z_admitted=[]; contrib=[]; finite=0; admitted=0
        i=start; safe=stop-(base.DELAY+base.HOLD)
        while i<safe:
            for s in base.FRESH:
                vals=data[s].loc[i,base.FULL].to_numpy(float)
                if not np.isfinite(vals).all(): continue
                finite+=1; per_symbol[s]['finite']+=1
                z=scaler.transform(np.asarray([vals],dtype=float))[0]; z_all.append(z)
                score=float(model.predict(np.asarray([vals],dtype=float))[0])
                if score<=0: continue
                admitted+=1; per_symbol[s]['admitted']+=1; z_admitted.append(z)
                m=float(np.max(np.abs(z))); per_symbol[s]['max_abs_z'].append(m)
                if m>3: per_symbol[s]['outside3']+=1
                contrib.append(z*ridge.coef_)
            i+=base.HOLD
        if not z_admitted: raise RuntimeError(f'fold {f}: no admitted fresh states')
        za=np.vstack(z_admitted); zf=np.vstack(z_all); cc=np.vstack(contrib)
        groups={}
        for g,features in GROUPS.items():
            idx=[base.FULL.index(x) for x in features]
            groups[g]={
                'mean_abs_admitted_train_z':float(np.mean(np.abs(za[:,idx]))),
                'mean_abs_all_fresh_train_z':float(np.mean(np.abs(zf[:,idx]))),
                'mean_signed_score_contribution_bps':float(np.mean(np.sum(cc[:,idx],axis=1))),
                'fraction_feature_values_abs_z_gt3':float(np.mean(np.abs(za[:,idx])>3.0)),
            }
        feature=[]
        for j,name in enumerate(base.FULL):
            feature.append({
                'feature':name,
                'mean_admitted_train_z':float(np.mean(za[:,j])),
                'mean_abs_admitted_train_z':float(np.mean(np.abs(za[:,j]))),
                'fraction_abs_z_gt3':float(np.mean(np.abs(za[:,j])>3.0)),
                'mean_score_contribution_bps':float(np.mean(cc[:,j])),
            })
        feature.sort(key=lambda r:(-r['mean_abs_admitted_train_z'],r['feature']))
        fold_rows.append({'fold':f,'finite_rows':finite,'admitted_rows':admitted,'admission_rate':admitted/finite,'groups':groups,'top_features_by_abs_training_z':feature[:10]})
        rows.extend(za.tolist())

    za=np.asarray(rows,dtype=float)
    group_rollup={}
    for g,features in GROUPS.items():
        idx=[base.FULL.index(x) for x in features]
        fold_g=[r['groups'][g] for r in fold_rows]
        group_rollup[g]={
            'mean_abs_admitted_train_z':float(np.mean([x['mean_abs_admitted_train_z'] for x in fold_g])),
            'fraction_feature_values_abs_z_gt3':float(np.mean([x['fraction_feature_values_abs_z_gt3'] for x in fold_g])),
            'mean_signed_score_contribution_bps':float(np.mean([x['mean_signed_score_contribution_bps'] for x in fold_g])),
        }
    dominant=sorted(group_rollup,key=lambda g:(-group_rollup[g]['mean_abs_admitted_train_z'],g))
    ps={}
    for s,v in per_symbol.items():
        ps[s]={
            'finite_rows':v['finite'],'admitted_rows':v['admitted'],'admission_rate':None if not v['finite'] else v['admitted']/v['finite'],
            'outside3_rate_among_admitted':None if not v['admitted'] else v['outside3']/v['admitted'],
            'median_max_abs_train_z':None if not v['max_abs_z'] else float(np.median(v['max_abs_z'])),
            'p90_max_abs_train_z':None if not v['max_abs_z'] else float(np.quantile(v['max_abs_z'],0.9)),
        }
    all_max=[]
    for s,v in per_symbol.items(): all_max.extend(v['max_abs_z'])
    result={
        'schema':'public_compute.fresh_scarcity_support_diagnostic.v1','generated_at':datetime.now(timezone.utc).isoformat(),
        'source':'exact already-public PR22 frozen confirmation capsule','common_cutoff':cutoff.isoformat(),'common_calendar_rows':len(cal),
        'train_universe':list(base.TRAIN),'fresh_universe':list(base.FRESH),'feature_groups_frozen_before_run':GROUPS,
        'overall_support':{
            'admitted_rows':len(all_max),'median_max_abs_train_z':float(np.median(all_max)),'p90_max_abs_train_z':float(np.quantile(all_max,0.9)),
            'outside_3sigma_rate':float(np.mean(np.asarray(all_max)>3.0)),
        },
        'group_support_rollup':group_rollup,'dominant_drift_groups':dominant,'per_symbol_support':ps,'fold_support':fold_rows,
        'decision_rule':{
            'uncertainty_first_if':'outside_3sigma_rate >= 0.20 OR any information group has >0.10 of admitted feature values beyond |z|=3',
            'controlled_nonlinearity_is_reasonable_if':'fresh states remain mostly within training support but ranking transport failed, implying mapping/interaction capacity rather than gross extrapolation',
            'thresholds_are_architecture triage only':'they do not admit trades, select symbols, or rescue the exposed fresh result'
        },
        'outcomes_used_for_feature_selection':False,'research_only':True,'promotion_authority':False,'runtime_mutation':False,'live_trading_change':False
    }
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print('FRESH_SCARCITY_SUPPORT_DIAGNOSTIC='+json.dumps(result,sort_keys=True))

if __name__=='__main__': main()
