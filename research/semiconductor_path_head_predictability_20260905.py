from __future__ import annotations

"""Development-only information test for terminal/MFE/adverse-excursion path heads.

No external semiconductor panels are loaded. The exact current 19-feature representation
is held fixed. One fixed shallow HGB regressor per target is trained chronology-cleanly
on the original seven-symbol domain. This experiment does NOT define a trading utility
or change admission/ranking; it asks whether path targets are learnable enough to justify
a later multi-task risk/duration architecture.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import research.fresh_scarcity_confirmation_20260905 as base

OUT=Path('semiconductor_path_head_predictability_20260905.json')
HOLD=20; DELAY=1
TARGETS=('terminal_net200_bps','mfe20_bps','adverse_excursion20_bps')


def model():
    return HistGradientBoostingRegressor(loss='squared_error',learning_rate=0.05,max_iter=120,max_leaf_nodes=8,max_depth=3,min_samples_leaf=80,l2_regularization=10.0,random_state=0)

def sp(a,b): return base.spearman(np.asarray(a,float),np.asarray(b,float))

def build_rows(data,prices,cal,folds):
    rows=[]
    for symbol in base.TRAIN:
        for fold,(start,stop) in enumerate(folds,start=1):
            safe=max(start,stop-(DELAY+HOLD))
            for i in range(start,safe):
                vals=data[symbol].loc[i,base.FULL].to_numpy(float)
                if not np.isfinite(vals).all():continue
                ei=i+DELAY; xi=ei+HOLD; entry=float(prices[symbol].iloc[ei]); path=prices[symbol].iloc[ei:xi+1].to_numpy(float)/entry-1.0
                terminal=float(path[-1]*10000.0-200.0); mfe=float(np.max(path)*10000.0); adverse=float(max(0.0,-np.min(path)*10000.0))
                row={'symbol':symbol,'fold':fold,'signal_i':i,'terminal_net200_bps':terminal,'mfe20_bps':mfe,'adverse_excursion20_bps':adverse}
                row.update({f:float(v) for f,v in zip(base.FULL,vals)})
                rows.append(row)
    return pd.DataFrame(rows)

def metric(pred,truth,baseline):
    mae=float(np.mean(np.abs(pred-truth))); bmae=float(np.mean(np.abs(baseline-truth)))
    return {'rows':int(len(truth)),'spearman':sp(pred,truth),'mae':mae,'median_baseline_mae':bmae,'mae_improvement_vs_median':bmae-mae}

def main():
    symbols=(*base.TRAIN,*base.CONTEXT); raw={s:base.load(s) for s in symbols}; cutoff=min(d.iloc[-1].timestamp for d in raw.values()); sets=[set(d.loc[d.timestamp<=cutoff,'timestamp']) for d in raw.values()]; cal=pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(cal)<1500:raise RuntimeError(f'insufficient calendar={len(cal)}')
    prices={s:raw[s].set_index('timestamp').price.reindex(cal) for s in raw}
    if any(v.isna().any() for v in prices.values()):raise RuntimeError('missing common-calendar price')
    old=base.FRESH;base.FRESH=()
    try:data=base.engineer(prices,cal)
    finally:base.FRESH=old
    folds=base.folds(len(cal)); frame=build_rows(data,prices,cal,folds)
    fold_results=[]; all_truth={t:[] for t in TARGETS}; all_pred={t:[] for t in TARGETS}; all_base={t:[] for t in TARGETS}
    for fold in range(2,7):
        start,_=folds[fold-1]; purge=DELAY+HOLD
        train=frame[frame.signal_i<start-purge].copy(); test=frame[frame.fold==fold].copy()
        if len(train)<1000 or len(test)<100:raise RuntimeError(f'fold {fold}: support train={len(train)} test={len(test)}')
        fr={'fold':fold}
        for target in TARGETS:
            m=model(); m.fit(train[base.FULL].to_numpy(float),train[target].to_numpy(float)); pred=m.predict(test[base.FULL].to_numpy(float)); truth=test[target].to_numpy(float); med=float(np.median(train[target])); baseline=np.full(len(test),med,float); met=metric(pred,truth,baseline); fr[target]=met
            all_truth[target].extend(truth.tolist());all_pred[target].extend(pred.tolist());all_base[target].extend(baseline.tolist())
        fold_results.append(fr)
    agg={}
    for target in TARGETS:
        agg[target]=metric(np.asarray(all_pred[target]),np.asarray(all_truth[target]),np.asarray(all_base[target])); agg[target]['positive_spearman_folds']=sum((r[target]['spearman'] or -1)>0 for r in fold_results); agg[target]['mae_better_folds']=sum(r[target]['mae_improvement_vs_median']>0 for r in fold_results)
    path_gate=bool(agg['mfe20_bps']['spearman']>0 and agg['adverse_excursion20_bps']['spearman']>0 and agg['mfe20_bps']['mae_improvement_vs_median']>0 and agg['adverse_excursion20_bps']['mae_improvement_vs_median']>0 and agg['mfe20_bps']['positive_spearman_folds']>=3 and agg['adverse_excursion20_bps']['positive_spearman_folds']>=3 and agg['mfe20_bps']['mae_better_folds']>=3 and agg['adverse_excursion20_bps']['mae_better_folds']>=3)
    out={'schema':'public_compute.semiconductor_path_head_predictability.v1','generated_at':datetime.now(timezone.utc).isoformat(),'development_universe':list(base.TRAIN),'exposed_external_panels_loaded':False,'common_cutoff':cutoff.isoformat(),'common_calendar_rows':len(cal),'representation':'exact current 19 features','learner':{'model':'fixed HistGradientBoostingRegressor','hyperparameters':{'learning_rate':0.05,'max_iter':120,'max_leaf_nodes':8,'max_depth':3,'min_samples_leaf':80,'l2_regularization':10.0,'random_state':0},'sweep':False},'targets':{'terminal_net200_bps':'fixed20 gross minus 200 bps','mfe20_bps':'maximum favorable excursion from +1 entry through +20','adverse_excursion20_bps':'positive magnitude of worst adverse excursion over same path'},'aggregate':agg,'folds':fold_results,'decision':'PATH_HEAD_INFORMATION_EVIDENCE' if path_gate else 'REJECT_PATH_HEAD_INFORMATION_WITH_CURRENT_REPRESENTATION','policy_or_utility_defined':False,'next_boundary':'a PASS justifies a separately frozen multi-task/risk-duration architecture experiment; it does not alter admission or ranking','research_only':True,'promotion_authority':False,'runtime_mutation':False,'live_trading_change':False}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print('SEMICONDUCTOR_PATH_HEAD_PREDICTABILITY='+json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
