from __future__ import annotations

"""Controlled nonlinear-capacity test for semiconductor scarcity ordering.

Development only: the exposed PR253/PR273 external panels are not loaded. The exact
19-feature Ridge remains the admission model, so the candidate set is identical between
arms. Ranking control uses the Ridge admission score. The sole challenger is one fixed,
shallow, regularized HistGradientBoostingRegressor trained on the same chronology-clean
prior target rows. No hyperparameter/model/feature/slot/cost sweep is allowed.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import research.fresh_scarcity_confirmation_20260905 as base

OUT = Path('semiconductor_controlled_nonlinear_ranker_20260905.json')
COST = 200.0


def hgb_model():
    return HistGradientBoostingRegressor(
        loss='squared_error', learning_rate=0.05, max_iter=120,
        max_leaf_nodes=8, max_depth=3, min_samples_leaf=80,
        l2_regularization=10.0, random_state=0,
    )


def mean(x): return None if not x else float(np.mean(x))
def sp(a,b): return base.spearman(np.asarray(a,float),np.asarray(b,float))

def summarize(rows, score_key):
    if not rows: return {'decisions':0}
    top=np.asarray([r[f'{score_key}_top']-COST for r in rows],float)
    ew=np.asarray([r['ew']-COST for r in rows],float)
    smh=np.asarray([r['smh']-COST for r in rows],float)
    ic=[r[f'{score_key}_ic'] for r in rows if r[f'{score_key}_ic'] is not None]
    return {
        'decisions':len(rows),'mean_top2_net200_bps':float(top.mean()),
        'mean_excess_vs_admitted_ew_bps':float((top-ew).mean()),
        'mean_excess_vs_smh_bps':float((top-smh).mean()),'mean_rank_ic':mean(ic),
    }


def main():
    # Development excludes every exposed external name by construction.
    symbols=(*base.TRAIN,*base.CONTEXT)
    raw={s:base.load(s) for s in symbols}
    cutoff=min(d.iloc[-1].timestamp for d in raw.values())
    sets=[set(d.loc[d.timestamp<=cutoff,'timestamp']) for d in raw.values()]
    cal=pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(cal)<1500: raise RuntimeError(f'insufficient development calendar={len(cal)}')
    prices={s:raw[s].set_index('timestamp').price.reindex(cal) for s in raw}
    if any(v.isna().any() for v in prices.values()): raise RuntimeError('missing development price')

    # base.engineer expects FRESH names; provide no access to them by temporarily making
    # the public fresh tuple empty, then restore it after feature construction.
    old_fresh=base.FRESH; base.FRESH=()
    try: data=base.engineer(prices,cal)
    finally: base.FRESH=old_fresh
    fs=base.folds(len(cal)); tr=base.frame(base.TRAIN,data,fs,base.FULL)

    decisions=[]
    for f in range(2,7):
        start,stop=fs[f-1]
        train=tr[tr.signal_i<start-base.PURGE]
        if len(train)<1000: raise RuntimeError(f'fold {f}: insufficient prior rows={len(train)}')
        ridge=base.fit(train,base.FULL)
        hgb=hgb_model(); hgb.fit(train[base.FULL].to_numpy(float),train.target.to_numpy(float))
        i=start; safe=stop-(base.DELAY+base.HOLD)
        while i<safe:
            ei=i+base.DELAY; xi=ei+base.HOLD; c=[]
            for s in base.TRAIN:
                vals=data[s].loc[i,base.FULL].to_numpy(float)
                if not np.isfinite(vals).all(): continue
                admission=float(ridge.predict(np.asarray([vals],float))[0])
                if admission<=0: continue
                nonlinear=float(hgb.predict(np.asarray([vals],float))[0])
                gross=float(prices[s].iloc[xi]/prices[s].iloc[ei]-1)*10000.0
                c.append({'symbol':s,'ridge':admission,'hgb':nonlinear,'gross':gross})
            if len(c)>=2:
                rc=sorted(c,key=lambda r:(-r['ridge'],r['symbol']))[:2]
                hc=sorted(c,key=lambda r:(-r['hgb'],r['symbol']))[:2]
                decisions.append({
                    'fold':f,'ridge_top':float(np.mean([r['gross'] for r in rc])),
                    'hgb_top':float(np.mean([r['gross'] for r in hc])),
                    'ew':float(np.mean([r['gross'] for r in c])),
                    'smh':float(prices['SMH'].iloc[xi]/prices['SMH'].iloc[ei]-1)*10000.0,
                    'ridge_ic':sp([r['ridge'] for r in c],[r['gross'] for r in c]),
                    'hgb_ic':sp([r['hgb'] for r in c],[r['gross'] for r in c]),
                })
            i+=base.HOLD

    folds=[]
    for f in range(2,7):
        fr=[r for r in decisions if r['fold']==f]
        rs=summarize(fr,'ridge'); hs=summarize(fr,'hgb')
        folds.append({'fold':f,'ridge':rs,'hgb':hs,
                      'hgb_minus_ridge_top2_bps':(hs.get('mean_top2_net200_bps') or 0)-(rs.get('mean_top2_net200_bps') or 0),
                      'hgb_minus_ridge_ic':(hs.get('mean_rank_ic') or 0)-(rs.get('mean_rank_ic') or 0)})
    ridge=summarize(decisions,'ridge'); hgb=summarize(decisions,'hgb')
    hgb.update({
        'ridge_beating_folds':sum(r['hgb_minus_ridge_top2_bps']>0 for r in folds),
        'positive_net_folds':sum((r['hgb'].get('mean_top2_net200_bps') or -1)>0 for r in folds),
        'ew_winning_folds':sum((r['hgb'].get('mean_excess_vs_admitted_ew_bps') or -1)>0 for r in folds),
        'smh_winning_folds':sum((r['hgb'].get('mean_excess_vs_smh_bps') or -1)>0 for r in folds),
        'positive_ic_folds':sum((r['hgb'].get('mean_rank_ic') or -1)>0 for r in folds),
        'ic_improvement_folds':sum(r['hgb_minus_ridge_ic']>0 for r in folds),
    })
    gate=bool(
        hgb['mean_top2_net200_bps']>ridge['mean_top2_net200_bps'] and
        hgb['mean_excess_vs_admitted_ew_bps']>0 and hgb['mean_excess_vs_smh_bps']>0 and
        (hgb['mean_rank_ic'] or -1)>0 and (hgb['mean_rank_ic'] or -1)>(ridge['mean_rank_ic'] or -1) and
        hgb['ridge_beating_folds']>=3 and hgb['smh_winning_folds']>=3 and
        hgb['positive_ic_folds']>=3 and hgb['ic_improvement_folds']>=3
    )
    out={
        'schema':'public_compute.semiconductor_controlled_nonlinear_ranker.v1',
        'generated_at':datetime.now(timezone.utc).isoformat(),'common_cutoff':cutoff.isoformat(),'common_calendar_rows':len(cal),
        'development_universe':list(base.TRAIN),'exposed_external_panels_loaded':False,
        'frozen_candidate_admission':'exact 19-feature Ridge predicted value > 0',
        'control':'same Ridge score orders admitted candidates',
        'challenger':{'model':'HistGradientBoostingRegressor','hyperparameters':{'learning_rate':0.05,'max_iter':120,'max_leaf_nodes':8,'max_depth':3,'min_samples_leaf':80,'l2_regularization':10.0,'random_state':0},'hyperparameter_sweep':False},
        'slots':2,'decision_spacing_sessions':20,'delay_sessions':1,'hold_sessions':20,'stress_cost_bps':200,
        'ridge':ridge,'hgb':hgb,'folds':folds,
        'decision':'CONTROLLED_NONLINEAR_RANKING_EVIDENCE' if gate else 'REJECT_CONTROLLED_NONLINEAR_RANKER',
        'next_boundary':'a development PASS still requires a new prospectively frozen external cohort; no exposed PR253/PR273 names may validate it',
        'research_only':True,'promotion_authority':False,'runtime_mutation':False,'live_trading_change':False
    }
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print('SEMICONDUCTOR_CONTROLLED_NONLINEAR='+json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
