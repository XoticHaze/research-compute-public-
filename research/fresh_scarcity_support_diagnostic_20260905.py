from __future__ import annotations

"""Fresh-cohort support diagnostic for the rejected scarcity confirmation."""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fresh_scarcity_confirmation_20260905 as base

OUT=Path('fresh_scarcity_support_diagnostic_20260905.json')
GROUPS={
'own_state':['mom5','mom20','mom60','mom100','mom20_z252','mom20_accel5','vol20','vol20_z252','distance_high60'],
'relative_state':['rs_smh20','rs_smh60','rs_qqq20','rs_qqq60'],
'market_context':['smh_mom20','smh_mom100','qqq_mom20','qqq_mom100'],
'breadth_cross_section':['survivor_breadth_positive20','survivor_cross_section_mom20_pct']}

def main():
 symbols=(*base.TRAIN,*base.FRESH,*base.CONTEXT); raw={s:base.load(s) for s in symbols}; cutoff=min(d.iloc[-1].timestamp for d in raw.values())
 sets=[set(d.loc[d.timestamp<=cutoff,'timestamp']) for d in raw.values()]; cal=pd.DatetimeIndex(sorted(set.intersection(*sets))); prices={s:raw[s].set_index('timestamp').price.reindex(cal) for s in raw}
 if len(cal)<1500 or any(v.isna().any() for v in prices.values()): raise RuntimeError('invalid common calendar')
 data=base.engineer(prices,cal); fs=base.folds(len(cal)); tr=base.frame(base.TRAIN,data,fs,base.FULL); fold_rows=[]; per_symbol={s:{'finite':0,'admitted':0,'outside3':0,'max':[]} for s in base.FRESH}
 for f in range(2,7):
  start,stop=fs[f-1]; train=tr[tr.signal_i<start-base.PURGE]; model=base.fit(train,base.FULL); scaler=model.named_steps['scale']; ridge=model.named_steps['ridge']; za=[]; zall=[]; cc=[]; finite=admitted=0; i=start; safe=stop-(base.DELAY+base.HOLD)
  while i<safe:
   for s in base.FRESH:
    vals=data[s].loc[i,base.FULL].to_numpy(float)
    if not np.isfinite(vals).all(): continue
    finite+=1; per_symbol[s]['finite']+=1; z=scaler.transform(np.asarray([vals]))[0]; zall.append(z); score=float(model.predict(np.asarray([vals]))[0])
    if score<=0: continue
    admitted+=1; per_symbol[s]['admitted']+=1; za.append(z); m=float(np.max(np.abs(z))); per_symbol[s]['max'].append(m); per_symbol[s]['outside3']+=int(m>3); cc.append(z*ridge.coef_)
   i+=base.HOLD
  if not za: raise RuntimeError(f'fold {f}: no admitted states')
  za=np.vstack(za); zall=np.vstack(zall); cc=np.vstack(cc); groups={}
  for g,features in GROUPS.items():
   idx=[base.FULL.index(x) for x in features]; groups[g]={'mean_abs_admitted_train_z':float(np.mean(np.abs(za[:,idx]))),'mean_abs_all_fresh_train_z':float(np.mean(np.abs(zall[:,idx]))),'fraction_feature_values_abs_z_gt3':float(np.mean(np.abs(za[:,idx])>3)),'mean_signed_score_contribution_bps':float(np.mean(np.sum(cc[:,idx],axis=1)))}
  fold_rows.append({'fold':f,'finite_rows':finite,'admitted_rows':admitted,'admission_rate':admitted/finite,'groups':groups})
 roll={g:{k:float(np.mean([r['groups'][g][k] for r in fold_rows])) for k in ('mean_abs_admitted_train_z','fraction_feature_values_abs_z_gt3','mean_signed_score_contribution_bps')} for g in GROUPS}; allmax=[x for v in per_symbol.values() for x in v['max']]; ps={s:{'finite_rows':v['finite'],'admitted_rows':v['admitted'],'admission_rate':v['admitted']/v['finite'] if v['finite'] else None,'outside3_rate_among_admitted':v['outside3']/v['admitted'] if v['admitted'] else None,'median_max_abs_train_z':float(np.median(v['max'])) if v['max'] else None} for s,v in per_symbol.items()}
 result={'schema':'public_compute.fresh_scarcity_support_diagnostic.v1','generated_at':datetime.now(timezone.utc).isoformat(),'common_cutoff':cutoff.isoformat(),'common_calendar_rows':len(cal),'train_universe':list(base.TRAIN),'fresh_universe':list(base.FRESH),'feature_groups_frozen_before_run':GROUPS,'overall_support':{'admitted_rows':len(allmax),'median_max_abs_train_z':float(np.median(allmax)),'p90_max_abs_train_z':float(np.quantile(allmax,.9)),'outside_3sigma_rate':float(np.mean(np.asarray(allmax)>3))},'group_support_rollup':roll,'dominant_drift_groups':sorted(roll,key=lambda g:(-roll[g]['mean_abs_admitted_train_z'],g)),'per_symbol_support':ps,'fold_support':fold_rows,'decision_rule':{'uncertainty_first_if':'outside_3sigma_rate >= 0.20 OR any information group has >0.10 of admitted feature values beyond |z|=3','controlled_nonlinearity_is_reasonable_if':'fresh states remain mostly within training support but ranking transport failed'},'outcomes_used_for_feature_selection':False,'research_only':True,'promotion_authority':False,'runtime_mutation':False,'live_trading_change':False}
 OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); print('FRESH_SCARCITY_SUPPORT_DIAGNOSTIC='+json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
