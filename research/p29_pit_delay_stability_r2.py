#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np
import p29_pit_causal_entry_delay_r1 as p29

DELAYS=tuple(range(0,11))

def main():
    # Diagnostic only: expand the predeclared execution delay grid without changing
    # membership, lookback, top-k, costs, or the underlying P29 selection rule.
    p29.DELAYS=DELAYS
    p29.main()
    path=Path('p29_pit_causal_entry_delay_r1.json')
    d=json.loads(path.read_text())
    rows=[]
    for delay in DELAYS:
        t=d['tests'][str(delay)]['50']
        rows.append({'delay_days':delay,'full_excess_vs_pit_ew':t['full']['excess_vs_pit_ew_cagr'],'full_positive_folds':t['full']['positive_folds_vs_pit_ew'],'recent_excess_vs_pit_ew':t['2022_forward']['excess_vs_pit_ew_cagr'],'recent_positive_folds':t['2022_forward']['positive_folds_vs_pit_ew'],'recent_excess_vs_smh':t['2022_forward']['excess_vs_smh_cagr']})
    full=np.array([r['full_excess_vs_pit_ew'] for r in rows],float); recent=np.array([r['recent_excess_vs_pit_ew'] for r in rows],float)
    out={'schema':'research.p29_pit_delay_stability_r2','parent':'P29','scientific_contract':{'selection_rule':'unchanged PIT semiconductor prior-6m top3','execution_delay_grid_days':list(DELAYS),'primary_cost_bps':50,'purpose':'diagnose whether causal-delay support is broad across plausible execution days rather than driven by one selected delay','no_delay_selection_or_tuning':True},'rows':rows,'stability':{'full_positive_delay_fraction':float((full>0).mean()),'full_median_excess':float(np.median(full)),'full_min_excess':float(full.min()),'full_max_excess':float(full.max()),'recent_positive_delay_fraction':float((recent>0).mean()),'recent_median_excess':float(np.median(recent)),'recent_min_excess':float(recent.min()),'recent_max_excess':float(recent.max())}}
    s=out['stability']; out['decision']='P29_EXECUTION_DAY_STABILITY_SUPPORTED' if s['full_positive_delay_fraction']>=0.8 and s['full_median_excess']>0 and s['recent_positive_delay_fraction']>=0.6 else 'P29_EXECUTION_DAY_STABILITY_MIXED'
    Path('p29_pit_delay_stability_r2.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
