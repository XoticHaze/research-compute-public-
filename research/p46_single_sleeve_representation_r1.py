from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import p46_alt_etf_representation_r2 as alt

ORIGINAL=('SPY','QQQ','TLT','GLD','DBC')
SUBS={'SPY':'VOO','QQQ':'VUG','TLT':'IEF','GLD':'IAU','DBC':'PDBC'}
BP=50


def evaluate(symbols):
    symbols=tuple(symbols)
    alt.SYMBOLS=symbols
    close=alt.base.load(symbols)
    current_month_start=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp()
    close=close.loc[close.index<current_month_start]
    f=alt.build(close)
    out=alt.score(f,BP)
    out['symbols']=list(symbols)
    out['source_panel_sha256']=alt.base.source_hash(close)
    return out


def main():
    original=evaluate(ORIGINAL)
    variants={}
    for old,new in SUBS.items():
        symbols=[new if s==old else s for s in ORIGINAL]
        variants[f'{old}_to_{new}']=evaluate(symbols)
    supported=[]
    for name,v in variants.items():
        supported.append(v['excess_cagr']>0 and v['positive_folds']>=3)
    decision='P46_SINGLE_SLEEVE_REPRESENTATION_ROBUST' if sum(supported)>=4 else 'P46_SINGLE_SLEEVE_REPRESENTATION_FRAGILE'
    out={
      'schema':'research.p46_single_sleeve_representation_r1',
      'parent':'P46',
      'hypothesis':'If the frozen P46 mechanism reflects broad economic sleeve selection rather than exact instrument identity, replacing one original ETF at a time with a close economic proxy should usually preserve after-cost matched-control excess.',
      'scientific_contract':{
        'original_representation':list(ORIGINAL),
        'single_substitutions':SUBS,
        'factors':['mom6','trend200','low_vol6','drawdown6'],
        'top_k':2,
        'cost_bps':BP,
        'matched_control':'same-universe equal weight over identical months for each representation',
        'chronological_folds':5,
        'support_rule':'at least 4 of 5 single-sleeve substitutions retain positive excess CAGR and >=3/5 positive folds',
        'no_parameter_factor_topk_or_weight_tuning':True,
        'representation_test_not_independent_source_test':True
      },
      'original_reproduction':original,
      'variants':variants,
      'supported_variant_count':int(sum(supported)),
      'decision':decision,
      'interpretation_rule':'Failure localizes representation fragility without selecting a preferred proxy. It weakens broad economic-mechanism generality but does not erase original-instrument historical evidence.'
    }
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/p46_single_sleeve_representation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out,sort_keys=True))


if __name__=='__main__': main()
