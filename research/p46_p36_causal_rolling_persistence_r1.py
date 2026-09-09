from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_p36_causal_temporal_holdout_r1 as causal

def roll_stats(f,w):
    rows=[]
    for i in range(w,len(f)+1):
        q=f.iloc[i-w:i]
        rows.append({'end':str(q.index[-1].date()),'excess_matched':causal.cagr(q.candidate)-causal.cagr(q.matched),'excess_qqq':causal.cagr(q.candidate)-causal.cagr(q.qqq)})
    em=np.array([x['excess_matched'] for x in rows]); eq=np.array([x['excess_qqq'] for x in rows])
    return {'window_months':w,'windows':len(rows),'positive_fraction_matched':float(np.mean(em>0)),'positive_fraction_qqq':float(np.mean(eq>0)),'median_excess_matched':float(np.median(em)),'median_excess_qqq':float(np.median(eq)),'worst_excess_matched':float(np.min(em)),'worst_excess_qqq':float(np.min(eq))}
def main():
    close=base.load(causal.ALL); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]; f=causal.build(close,50,1)
    tests={'36m':roll_stats(f,36),'60m':roll_stats(f,60)}; state='CAUSAL_ROLLING_MATCHED_PERSISTENCE_STRONG_QQQ_MIXED' if tests['60m']['positive_fraction_matched']>=.8 and tests['60m']['positive_fraction_qqq']<.8 else 'CAUSAL_ROLLING_PERSISTENCE_STRONG' if tests['60m']['positive_fraction_matched']>=.8 and tests['60m']['positive_fraction_qqq']>=.8 else 'CAUSAL_ROLLING_PERSISTENCE_CAUTION'
    out={'schema':'research.p46_p36_causal_rolling_persistence_r1','parents':['P46','P36'],'scientific_contract':{'implementation':'fixed one-trading-day delayed entry at 50 bps','rolling_windows_months':[36,60],'comparators':['exact matched blend','QQQ'],'no_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_causal_rolling_persistence_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
