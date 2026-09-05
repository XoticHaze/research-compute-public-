from __future__ import annotations

"""Development-only target-architecture discriminator for semiconductor scarcity.

After direct-return HGB improved development economics but failed fresh rank-IC/SMH
confirmation, test a role-matched target instead of tuning learner capacity: probability
that a candidate clears the actual 200 bps scarcity hurdle over +1/fixed20.

Candidate admission remains the exact 19-feature Ridge > 0. Control ranking is the fixed
PR26 direct-return HGB. Challenger is one fixed HistGradientBoostingClassifier on the
same 19 features with target gross_fixed20_bps > 200. No external panels are loaded,
no hyperparameter/model/feature/slot/cost sweep is permitted.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

import research.fresh_scarcity_confirmation_20260905 as base

OUT=Path('semiconductor_hurdle_probability_ranker_20260905.json')
COST=200.0


def regressor():
    return HistGradientBoostingRegressor(loss='squared_error',learning_rate=0.05,max_iter=120,max_leaf_nodes=8,max_depth=3,min_samples_leaf=80,l2_regularization=10.0,random_state=0)

def classifier():
    return HistGradientBoostingClassifier(loss='log_loss',learning_rate=0.05,max_iter=120,max_leaf_nodes=8,max_depth=3,min_samples_leaf=80,l2_regularization=10.0,random_state=0)

def mean(x): return None if not x else float(np.mean(x))
def sp(a,b): return base.spearman(np.asarray(a,float),np.asarray(b,float))

def summarize(rows,key):
    if not rows:return {'decisions':0}
    top=np.asarray([r[f'{key}_top']-COST for r in rows],float); ew=np.asarray([r['ew']-COST for r in rows],float); smh=np.asarray([r['smh']-COST for r in rows],float)
    ic=[r[f'{key}_ic'] for r in rows if r[f'{key}_ic'] is not None]
    clear=[r[f'{key}_clear_rate'] for r in rows]
    return {'decisions':len(rows),'mean_top2_net200_bps':float(top.mean()),'mean_excess_vs_admitted_ew_bps':float((top-ew).mean()),'mean_excess_vs_smh_bps':float((top-smh).mean()),'mean_rank_ic':mean(ic),'selected_clear200_rate':float(np.mean(clear))}

def main():
    symbols=(*base.TRAIN,*base.CONTEXT); raw={s:base.load(s) for s in symbols}; cutoff=min(d.iloc[-1].timestamp for d in raw.values()); sets=[set(d.loc[d.timestamp<=cutoff,'timestamp']) for d in raw.values()]; cal=pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(cal)<1500: raise RuntimeError(f'insufficient development calendar={len(cal)}')
    prices={s:raw[s].set_index('timestamp').price.reindex(cal) for s in raw}
    if any(v.isna().any() for v in prices.values()): raise RuntimeError('missing development price')
    old=base.FRESH; base.FRESH=()
    try:data=base.engineer(prices,cal)
    finally:base.FRESH=old
    fs=base.folds(len(cal)); tr=base.frame(base.TRAIN,data,fs,base.FULL)
    decisions=[]; class_balance=[]
    for f in range(2,7):
        start,stop=fs[f-1]; train=tr[tr.signal_i<start-base.PURGE].copy()
        if len(train)<1000: raise RuntimeError(f'fold {f}: insufficient prior rows={len(train)}')
        # base target is gross fixed20 bps minus the frozen 25 bps training friction.
        # Therefore gross > 200 iff target > 175.
        y=(train.target.to_numpy(float) > (COST-base.COST_TRAIN)).astype(int)
        positive=float(np.mean(y)); class_balance.append({'fold':f,'train_rows':len(train),'clear200_rate':positive})
        if positive<=0 or positive>=1: raise RuntimeError(f'fold {f}: degenerate hurdle target rate={positive}')
        admission=base.fit(train,base.FULL); direct=regressor(); direct.fit(train[base.FULL].to_numpy(float),train.target.to_numpy(float)); hurdle=classifier(); hurdle.fit(train[base.FULL].to_numpy(float),y)
        i=start; safe=stop-(base.DELAY+base.HOLD)
        while i<safe:
            ei=i+base.DELAY; xi=ei+base.HOLD; c=[]
            for s in base.TRAIN:
                vals=data[s].loc[i,base.FULL].to_numpy(float)
                if not np.isfinite(vals).all():continue
                admit=float(admission.predict(np.asarray([vals],float))[0])
                if admit<=0:continue
                ds=float(direct.predict(np.asarray([vals],float))[0]); hp=float(hurdle.predict_proba(np.asarray([vals],float))[0,1]); gross=float(prices[s].iloc[xi]/prices[s].iloc[ei]-1)*10000.0
                c.append({'symbol':s,'direct':ds,'hurdle':hp,'gross':gross})
            if len(c)>=2:
                dc=sorted(c,key=lambda r:(-r['direct'],r['symbol']))[:2]; hc=sorted(c,key=lambda r:(-r['hurdle'],r['symbol']))[:2]
                decisions.append({'fold':f,'direct_top':float(np.mean([r['gross'] for r in dc])),'hurdle_top':float(np.mean([r['gross'] for r in hc])),'ew':float(np.mean([r['gross'] for r in c])),'smh':float(prices['SMH'].iloc[xi]/prices['SMH'].iloc[ei]-1)*10000.0,'direct_ic':sp([r['direct'] for r in c],[r['gross'] for r in c]),'hurdle_ic':sp([r['hurdle'] for r in c],[r['gross'] for r in c]),'direct_clear_rate':float(np.mean([r['gross']>COST for r in dc])),'hurdle_clear_rate':float(np.mean([r['gross']>COST for r in hc]))})
            i+=base.HOLD
    folds=[]
    for f in range(2,7):
        fr=[r for r in decisions if r['fold']==f]; ds=summarize(fr,'direct'); hs=summarize(fr,'hurdle'); folds.append({'fold':f,'direct':ds,'hurdle':hs,'hurdle_minus_direct_top2_bps':(hs.get('mean_top2_net200_bps') or 0)-(ds.get('mean_top2_net200_bps') or 0),'hurdle_minus_direct_ic':(hs.get('mean_rank_ic') or 0)-(ds.get('mean_rank_ic') or 0),'clear_rate_delta':(hs.get('selected_clear200_rate') or 0)-(ds.get('selected_clear200_rate') or 0)})
    direct=summarize(decisions,'direct'); hurdle=summarize(decisions,'hurdle')
    hurdle.update({'direct_beating_folds':sum(r['hurdle_minus_direct_top2_bps']>0 for r in folds),'clear_rate_improvement_folds':sum(r['clear_rate_delta']>0 for r in folds),'positive_net_folds':sum((r['hurdle'].get('mean_top2_net200_bps') or -1)>0 for r in folds),'ew_winning_folds':sum((r['hurdle'].get('mean_excess_vs_admitted_ew_bps') or -1)>0 for r in folds),'smh_winning_folds':sum((r['hurdle'].get('mean_excess_vs_smh_bps') or -1)>0 for r in folds),'positive_ic_folds':sum((r['hurdle'].get('mean_rank_ic') or -1)>0 for r in folds),'ic_improvement_folds':sum(r['hurdle_minus_direct_ic']>0 for r in folds)})
    gate=bool(hurdle['mean_top2_net200_bps']>direct['mean_top2_net200_bps'] and hurdle['selected_clear200_rate']>direct['selected_clear200_rate'] and hurdle['mean_excess_vs_admitted_ew_bps']>0 and hurdle['mean_excess_vs_smh_bps']>0 and (hurdle['mean_rank_ic'] or -1)>0 and hurdle['direct_beating_folds']>=3 and hurdle['clear_rate_improvement_folds']>=3 and hurdle['smh_winning_folds']>=3 and hurdle['positive_ic_folds']>=3)
    out={'schema':'public_compute.semiconductor_hurdle_probability_ranker.v1','generated_at':datetime.now(timezone.utc).isoformat(),'development_universe':list(base.TRAIN),'exposed_external_panels_loaded':False,'common_cutoff':cutoff.isoformat(),'common_calendar_rows':len(cal),'candidate_admission':'exact 19-feature Ridge predicted value > 0','control':{'target':'fixed20 after25 continuous value','model':'fixed shallow HGB from PR26'},'challenger':{'target':'gross fixed20 return > 200 bps','equivalent_training_label':'after25 target > 175 bps','model':'fixed HistGradientBoostingClassifier','hyperparameters':{'learning_rate':0.05,'max_iter':120,'max_leaf_nodes':8,'max_depth':3,'min_samples_leaf':80,'l2_regularization':10.0,'random_state':0},'hyperparameter_sweep':False},'train_hurdle_class_balance':class_balance,'direct_return_hgb':direct,'hurdle_probability':hurdle,'folds':folds,'decision':'HURDLE_PROBABILITY_RANKING_EVIDENCE' if gate else 'REJECT_HURDLE_PROBABILITY_RANKER','next_boundary':'development PASS requires a separately frozen untouched external cohort; no exposed external names may validate it','research_only':True,'promotion_authority':False,'runtime_mutation':False,'live_trading_change':False}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); print('SEMICONDUCTOR_HURDLE_PROBABILITY='+json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
