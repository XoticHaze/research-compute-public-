from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_p36_causal_temporal_holdout_r1 as causal

def score(f):
 return {'months':len(f),'excess_vs_matched_cagr':causal.cagr(f.candidate)-causal.cagr(f.matched),'excess_vs_qqq_cagr':causal.cagr(f.candidate)-causal.cagr(f.qqq)}
def main():
 close=base.load(causal.ALL); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]; f=causal.build(close,50,1).loc[pd.Timestamp('2022-01-01'):].copy(); f['monthly_excess']=f.candidate-f.matched; tests={'full':score(f)}
 for k in (1,3,5):
  drop=f.nlargest(k,'monthly_excess').index; tests[f'remove_top_{k}']=score(f.drop(index=drop))
 state='CAUSAL_RECENT_NOT_TOP5_DEPENDENT' if tests['remove_top_5']['excess_vs_matched_cagr']>0 else 'CAUSAL_RECENT_TOP5_CONCENTRATED'; out={'schema':'research.p46_p36_causal_recent_concentration_r1','parents':['P46','P36'],'scientific_contract':{'implementation':'fixed one-trading-day delayed entry at 50 bps','window':'2022-forward complete months','stress':['remove top 1 candidate-minus-matched month','remove top 3','remove top 5'],'comparators':['exact matched blend','QQQ'],'no_parameter_or_weight_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_causal_recent_concentration_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
