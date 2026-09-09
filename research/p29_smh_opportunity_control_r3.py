from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import p29_pit_delay_stability_r2 as stability

DELAYS=tuple(range(0,11)); BP='50'


def main():
    stability.main()
    raw=json.loads(Path('p29_pit_causal_entry_delay_r1.json').read_text())
    rows=[]
    for delay in DELAYS:
        t=raw['tests'][str(delay)][BP]
        full=t['full']; recent=t['2022_forward']
        rows.append({
          'delay_days':delay,
          'full_excess_vs_pit_ew':full['excess_vs_pit_ew_cagr'],
          'full_excess_vs_smh':full['excess_vs_smh_cagr'],
          'full_positive_folds_vs_pit_ew':full['positive_folds_vs_pit_ew'],
          'full_positive_folds_vs_smh':full['positive_folds_vs_smh'],
          'recent_excess_vs_pit_ew':recent['excess_vs_pit_ew_cagr'],
          'recent_excess_vs_smh':recent['excess_vs_smh_cagr'],
          'recent_positive_folds_vs_pit_ew':recent['positive_folds_vs_pit_ew'],
          'recent_positive_folds_vs_smh':recent['positive_folds_vs_smh'],
        })
    full=np.asarray([r['full_excess_vs_smh'] for r in rows],float)
    recent=np.asarray([r['recent_excess_vs_smh'] for r in rows],float)
    full_fold=np.asarray([r['full_positive_folds_vs_smh'] for r in rows],int)
    recent_fold=np.asarray([r['recent_positive_folds_vs_smh'] for r in rows],int)
    summary={
      'full_positive_delay_fraction_vs_smh':float((full>0).mean()),
      'full_delay_fraction_3of5_folds_vs_smh':float((full_fold>=3).mean()),
      'full_median_excess_vs_smh':float(np.median(full)),
      'full_min_excess_vs_smh':float(full.min()),
      'full_max_excess_vs_smh':float(full.max()),
      'recent_positive_delay_fraction_vs_smh':float((recent>0).mean()),
      'recent_delay_fraction_3of5_folds_vs_smh':float((recent_fold>=3).mean()),
      'recent_median_excess_vs_smh':float(np.median(recent)),
      'recent_min_excess_vs_smh':float(recent.min()),
      'recent_max_excess_vs_smh':float(recent.max()),
    }
    supported=(summary['full_positive_delay_fraction_vs_smh']>=0.8 and summary['full_delay_fraction_3of5_folds_vs_smh']>=0.6 and summary['recent_positive_delay_fraction_vs_smh']>=0.6 and summary['recent_median_excess_vs_smh']>0)
    out={
      'schema':'research.p29_smh_opportunity_control_r3','parent':'P29',
      'hypothesis':'The point-in-time semiconductor top-3 momentum selector remains economically useful versus the investable SMH opportunity control across a broad prospectively fixed 0-10 trading-day execution-delay surface, not merely versus PIT semiconductor equal weight.',
      'scientific_contract':{
        'selection_rule':'unchanged PIT S&P500 semiconductor membership, prior-6m momentum, top3 equal weight',
        'execution_delay_grid_days':list(DELAYS),'cost_bps':50,
        'primary_matched_control':'same eligible PIT semiconductor equal weight over identical delayed intervals',
        'opportunity_control':'SMH over identical delayed intervals',
        'windows':['full','2022_forward'],'no_delay_selection_or_tuning':True
      },
      'rows':rows,'summary':summary,
      'decision':'P29_SMH_OPPORTUNITY_COST_SUPPORTED' if supported else 'P29_SMH_OPPORTUNITY_COST_WEAK'
    }
    Path('p29_smh_opportunity_control_r3.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
