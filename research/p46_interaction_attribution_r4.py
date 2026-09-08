from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import p46_deep_robustness_r2 as r2

START=pd.Timestamp('2015-07-31')
CASES={
 'original':('SPY','QQQ','TLT','GLD','DBC'),
 'single_TLT_to_IEF':('SPY','QQQ','IEF','GLD','DBC'),
 'single_DBC_to_PDBC':('SPY','QQQ','TLT','GLD','PDBC'),
 'pair_TLT_DBC_to_IEF_PDBC':('SPY','QQQ','IEF','GLD','PDBC'),
}

def stats(fr):
 f=fr.loc[START:].copy(); out=r2.pack(f)
 c=f.gross-f.turnover*.0025; x=c-f.ew
 out['attribution']={
  'mean_annual_turnover':float(f.turnover.mean()*12),
  'annualized_arithmetic_excess_25':float(x.mean()*12),
  'monthly_excess_positive_share_25':float((x>0).mean()),
  'monthly_excess_median_25':float(x.median()),
 }
 return out

def main():
 tests={}
 for name,syms in CASES.items():
  fr,close=r2.run(syms); tests[name]={'symbols':list(syms),'source_sha256':r2.base.source_hash(close),**stats(fr)}
 out={'schema':'research.p46_interaction_attribution_r4','parent':'P46','scientific_contract':{'matched_start':str(START.date()),'cases':{k:list(v) for k,v in CASES.items()},'score':'unchanged four-factor equal-rank composite','top_k':2,'cadence':'monthly','costs_bps':[25,50],'comparator':'same-case equal weight','no_parameter_tuning':True},'tests':tests}
 Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_interaction_attribution_r4.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({k:{'excess25':v['25']['excess_cagr'],'folds25':v['25']['positive_folds'],'excess50':v['50']['excess_cagr'],'turnover':v['attribution']['mean_annual_turnover'],'arith_excess25':v['attribution']['annualized_arithmetic_excess_25'],'positive_month_share':v['attribution']['monthly_excess_positive_share_25']} for k,v in tests.items()},sort_keys=True))
if __name__=='__main__': main()
