from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_p36_causal_temporal_holdout_r1 as causal

def block_boot(x, block=6, n=4000, seed=4636):
    x=np.asarray(x,float); rng=np.random.default_rng(seed); L=len(x); vals=[]
    for _ in range(n):
        draw=[]
        while len(draw)<L:
            s=int(rng.integers(0,max(1,L-block+1))); draw.extend(x[s:s+block])
        vals.append(float(np.mean(draw[:L])*12))
    a=np.asarray(vals); q=np.quantile(a,[.025,.5,.975])
    return {'annualized_mean_excess':float(np.mean(x)*12),'bootstrap_95pct':[float(q[0]),float(q[2])],'bootstrap_median':float(q[1]),'p_annualized_excess_le_zero':float(np.mean(a<=0)),'replications':n,'block_months':block}
def main():
    close=base.load(causal.ALL); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]
    full=causal.build(close,50,1); recent=full.loc[pd.Timestamp('2022-01-01'):]
    tests={}
    for name,f in [('full',full),('2022_forward',recent)]:
        tests[name]={'vs_matched':block_boot((f.candidate-f.matched).to_numpy()),'vs_qqq':block_boot((f.candidate-f.qqq).to_numpy(),seed=4637)}
    state='CAUSAL_BLOCK_BOOTSTRAP_SUPPORTED' if tests['full']['vs_matched']['p_annualized_excess_le_zero']<=.05 and tests['2022_forward']['vs_matched']['p_annualized_excess_le_zero']<=.10 else 'CAUSAL_BLOCK_BOOTSTRAP_CAUTION'
    out={'schema':'research.p46_p36_causal_block_bootstrap_r1','parents':['P46','P36'],'scientific_contract':{'implementation':'fixed one-trading-day delayed entry at 50 bps','bootstrap':'moving contiguous 6-month blocks','replications':4000,'windows':['full complete-month history','2022-forward'],'comparators':['exact matched blend','QQQ'],'no_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':state}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_causal_block_bootstrap_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
