from __future__ import annotations
import itertools, json
from pathlib import Path
import pandas as pd
import p46_single_sleeve_representation_r1 as one

ORIGINAL=one.ORIGINAL
SUBS=one.SUBS
BP=50


def main():
    tests={}
    keys=list(SUBS)
    for a,b in itertools.combinations(keys,2):
        symbols=[SUBS[s] if s in (a,b) else s for s in ORIGINAL]
        r=one.evaluate(symbols)
        tests[f'{a}_to_{SUBS[a]}__{b}_to_{SUBS[b]}']=r
    supported={k:(v['excess_cagr']>0 and v['positive_folds']>=3) for k,v in tests.items()}
    n=sum(supported.values())
    out={
      'schema':'research.p46_pairwise_representation_r1',
      'parent':'P46',
      'hypothesis':'Because all five single-sleeve proxy substitutions survived but the simultaneous five-sleeve transport failed, test whether representation fragility emerges already from pairwise proxy interactions.',
      'scientific_contract':{
        'original_representation':list(ORIGINAL),'substitutions':SUBS,'cost_bps':BP,'top_k':2,
        'factors':['mom6','trend200','low_vol6','drawdown6'],
        'matched_control':'same-universe equal weight over identical months for each pair',
        'support_per_pair':'positive excess CAGR and >=3/5 positive chronological folds',
        'no_pair_selection_or_parameter_tuning':True
      },
      'tests':tests,'supported_pairs':supported,'supported_pair_count':int(n),
      'decision':'P46_PAIRWISE_REPRESENTATION_INTERACTION_FRAGILE' if n<8 else 'P46_PAIRWISE_REPRESENTATION_MOSTLY_ROBUST',
      'interpretation_rule':'This is interaction localization only. It must not be used to choose a preferred proxy pair ex post.'
    }
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p46_pairwise_representation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
