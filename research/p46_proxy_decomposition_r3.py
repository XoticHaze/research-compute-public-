from __future__ import annotations
import json
from pathlib import Path
import p46_deep_robustness_r2 as r2

CASES={
 'single_TLT_to_IEF':('SPY','QQQ','IEF','GLD','DBC'),
 'single_GLD_to_IAU':('SPY','QQQ','TLT','IAU','DBC'),
 'single_DBC_to_PDBC':('SPY','QQQ','TLT','GLD','PDBC'),
 'pair_TLT_GLD_to_IEF_IAU':('SPY','QQQ','IEF','IAU','DBC'),
 'pair_TLT_DBC_to_IEF_PDBC':('SPY','QQQ','IEF','GLD','PDBC'),
 'pair_GLD_DBC_to_IAU_PDBC':('SPY','QQQ','TLT','IAU','PDBC'),
}

def main():
 tests={}
 for name,syms in CASES.items():
  fr,close=r2.run(syms); tests[name]={'symbols':list(syms),'source_sha256':r2.base.source_hash(close),**r2.pack(fr)}
 out={'schema':'research.p46_proxy_decomposition_r3','parent':'P46','scientific_contract':{'base':['SPY','QQQ','TLT','GLD','DBC'],'replacement_map':{'TLT':'IEF','GLD':'IAU','DBC':'PDBC'},'score':'unchanged four-factor equal-rank composite','top_k':2,'cadence':'monthly','costs_bps':[25,50],'comparator':'same-case equal weight','no_weight_or_lookback_tuning':True},'tests':tests}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_proxy_decomposition_r3.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:{'excess25':v['25']['excess_cagr'],'folds25':v['25']['positive_folds'],'excess50':v['50']['excess_cagr'],'start':v['25']['start']} for k,v in tests.items()},sort_keys=True))
if __name__=='__main__': main()
