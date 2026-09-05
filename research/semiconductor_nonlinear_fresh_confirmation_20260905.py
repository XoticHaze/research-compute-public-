from __future__ import annotations

"""Fresh external confirmation of PR26 controlled nonlinear scarcity ranking.

Cohort and gate were frozen before target evaluation in
semiconductor_nonlinear_fresh_confirmation_contract_20260905.json. The exact Ridge
admission and fixed shallow HGB challenger from PR26 are unchanged. Previously exposed
PR253/PR273 symbols are never loaded. Training-support diagnostics are report-only;
no filtering/rescue rule is authorized on this panel.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import research.fresh_scarcity_confirmation_20260905 as base

CONTRACT=Path('research/semiconductor_nonlinear_fresh_confirmation_contract_20260905.json')
OUT=Path('semiconductor_nonlinear_fresh_confirmation_20260905.json')
COST=200.0


def hgb_model():
    return HistGradientBoostingRegressor(loss='squared_error',learning_rate=0.05,max_iter=120,max_leaf_nodes=8,max_depth=3,min_samples_leaf=80,l2_regularization=10.0,random_state=0)

def mean(x): return None if not x else float(np.mean(x))
def sp(a,b): return base.spearman(np.asarray(a,float),np.asarray(b,float))
def summarize(rows,key):
    if not rows:return {'decisions':0}
    top=np.asarray([r[f'{key}_top']-COST for r in rows],float); ew=np.asarray([r['ew']-COST for r in rows],float); smh=np.asarray([r['smh']-COST for r in rows],float)
    ic=[r[f'{key}_ic'] for r in rows if r[f'{key}_ic'] is not None]
    return {'decisions':len(rows),'mean_top2_net200_bps':float(top.mean()),'mean_excess_vs_admitted_ew_bps':float((top-ew).mean()),'mean_excess_vs_smh_bps':float((top-smh).mean()),'mean_rank_ic':mean(ic)}

def main():
    c=json.loads(CONTRACT.read_text()); fresh=tuple(c['fresh_confirmation_universe']); train_symbols=tuple(c['train_universe'])
    assert set(fresh).isdisjoint(train_symbols); assert set(fresh).isdisjoint(c['spent_external_universe_pr253']); assert set(fresh).isdisjoint(c['spent_external_universe_pr273'])
    assert c['ranking_challenger']['hyperparameters']=={'learning_rate':0.05,'max_iter':120,'max_leaf_nodes':8,'max_depth':3,'min_samples_leaf':80,'l2_regularization':10.0,'random_state':0}
    symbols=(*train_symbols,*fresh,*base.CONTEXT); raw={s:base.load(s) for s in symbols}; cutoff=min(d.iloc[-1].timestamp for d in raw.values()); sets=[set(d.loc[d.timestamp<=cutoff,'timestamp']) for d in raw.values()]; cal=pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(cal)!=3186: raise RuntimeError(f'fresh source parity changed common_calendar={len(cal)}')
    prices={s:raw[s].set_index('timestamp').price.reindex(cal) for s in raw}
    if any(v.isna().any() for v in prices.values()): raise RuntimeError('missing common-calendar price')
    old=base.FRESH; base.FRESH=fresh
    try:data=base.engineer(prices,cal)
    finally:base.FRESH=old
    fs=base.folds(len(cal)); tr=base.frame(train_symbols,data,fs,base.FULL); decisions=[]; support=[]
    for f in range(2,7):
        start,stop=fs[f-1]; train=tr[tr.signal_i<start-base.PURGE]
        if len(train)<1000: raise RuntimeError(f'fold {f}: insufficient train rows={len(train)}')
        ridge=base.fit(train,base.FULL); scaler=ridge.named_steps['scale']; hgb=hgb_model(); hgb.fit(train[base.FULL].to_numpy(float),train.target.to_numpy(float))
        i=start; safe=stop-(base.DELAY+base.HOLD)
        while i<safe:
            ei=i+base.DELAY; xi=ei+base.HOLD; cc=[]
            for s in fresh:
                vals=data[s].loc[i,base.FULL].to_numpy(float)
                if not np.isfinite(vals).all():continue
                rs=float(ridge.predict(np.asarray([vals],float))[0])
                if rs<=0:continue
                hs=float(hgb.predict(np.asarray([vals],float))[0]); gross=float(prices[s].iloc[xi]/prices[s].iloc[ei]-1)*10000.0; mz=float(np.max(np.abs(scaler.transform(np.asarray([vals],float))[0])))
                support.append({'fold':f,'symbol':s,'max_abs_train_z':mz}); cc.append({'symbol':s,'ridge':rs,'hgb':hs,'gross':gross})
            if len(cc)>=2:
                rc=sorted(cc,key=lambda r:(-r['ridge'],r['symbol']))[:2]; hc=sorted(cc,key=lambda r:(-r['hgb'],r['symbol']))[:2]
                decisions.append({'fold':f,'ridge_top':float(np.mean([r['gross'] for r in rc])),'hgb_top':float(np.mean([r['gross'] for r in hc])),'ew':float(np.mean([r['gross'] for r in cc])),'smh':float(prices['SMH'].iloc[xi]/prices['SMH'].iloc[ei]-1)*10000.0,'ridge_ic':sp([r['ridge'] for r in cc],[r['gross'] for r in cc]),'hgb_ic':sp([r['hgb'] for r in cc],[r['gross'] for r in cc])})
            i+=base.HOLD
    folds=[]
    for f in range(2,7):
        fr=[r for r in decisions if r['fold']==f]; rs=summarize(fr,'ridge'); hs=summarize(fr,'hgb'); folds.append({'fold':f,'ridge':rs,'hgb':hs,'hgb_minus_ridge_top2_bps':(hs.get('mean_top2_net200_bps') or 0)-(rs.get('mean_top2_net200_bps') or 0),'hgb_minus_ridge_ic':(hs.get('mean_rank_ic') or 0)-(rs.get('mean_rank_ic') or 0)})
    ridge=summarize(decisions,'ridge'); hgb=summarize(decisions,'hgb')
    hgb.update({'ridge_beating_folds':sum(r['hgb_minus_ridge_top2_bps']>0 for r in folds),'positive_net_folds':sum((r['hgb'].get('mean_top2_net200_bps') or -1)>0 for r in folds),'ew_winning_folds':sum((r['hgb'].get('mean_excess_vs_admitted_ew_bps') or -1)>0 for r in folds),'smh_winning_folds':sum((r['hgb'].get('mean_excess_vs_smh_bps') or -1)>0 for r in folds),'positive_ic_folds':sum((r['hgb'].get('mean_rank_ic') or -1)>0 for r in folds),'ic_improvement_folds':sum(r['hgb_minus_ridge_ic']>0 for r in folds)})
    z=np.asarray([r['max_abs_train_z'] for r in support],float); by_symbol={}
    for s in fresh:
        v=np.asarray([r['max_abs_train_z'] for r in support if r['symbol']==s],float); by_symbol[s]={'admitted_rows':int(len(v)),'median_max_abs_train_z':None if not len(v) else float(np.median(v)),'outside3_rate':None if not len(v) else float(np.mean(v>3.0))}
    support_summary={'admitted_rows':int(len(z)),'median_max_abs_train_z':float(np.median(z)),'p90_max_abs_train_z':float(np.quantile(z,0.9)),'outside3_rate':float(np.mean(z>3.0)),'per_symbol':by_symbol,'filter_applied':False}
    gate=bool(hgb['mean_top2_net200_bps']>0 and hgb['mean_excess_vs_admitted_ew_bps']>0 and hgb['mean_excess_vs_smh_bps']>0 and (hgb['mean_rank_ic'] or -1)>0 and hgb['mean_top2_net200_bps']>ridge['mean_top2_net200_bps'] and (hgb['mean_rank_ic'] or -1)>(ridge['mean_rank_ic'] or -1) and hgb['ridge_beating_folds']>=3 and hgb['smh_winning_folds']>=3 and hgb['positive_ic_folds']>=3 and hgb['ic_improvement_folds']>=3)
    out={'schema':'public_compute.semiconductor_nonlinear_fresh_confirmation.v1','generated_at':datetime.now(timezone.utc).isoformat(),'contract_head':c['development_parent_head'],'fresh_universe':list(fresh),'common_cutoff':cutoff.isoformat(),'common_calendar_rows':len(cal),'ridge':ridge,'hgb':hgb,'folds':folds,'support_report_only':support_summary,'decision':'CONFIRM_CONTROLLED_NONLINEAR_SCARCITY_RANKER' if gate else 'REJECT_FRESH_CONTROLLED_NONLINEAR_SCARCITY_RANKER','research_only':True,'promotion_authority':False,'runtime_mutation':False,'live_trading_change':False}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); print('SEMICONDUCTOR_NONLINEAR_FRESH_CONFIRMATION='+json.dumps(out,sort_keys=True))
if __name__=='__main__':main()
