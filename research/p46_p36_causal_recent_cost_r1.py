from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_p36_causal_temporal_holdout_r1 as causal

def cagr(x):
    return causal.cagr(x)

def gross_frame(close):
    zero=causal.build(close,0,1)
    hundred=causal.build(close,100,1)
    # At fixed signals/weights, the difference between 0 and 100 bps is the realized turnover cost.
    turnover=(zero.candidate-hundred.candidate)*100.0
    return pd.DataFrame({'gross':zero.candidate,'turnover':turnover,'matched':zero.matched,'qqq':zero.qqq},index=zero.index)

def main():
    close=base.load(causal.ALL); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]
    f=gross_frame(close).loc[pd.Timestamp('2022-01-01'):]; rows=[]
    for bp in range(0,301,5):
        cand=f.gross-f.turnover*bp/10000
        rows.append({'bps':bp,'excess_matched':cagr(cand)-cagr(f.matched),'excess_qqq':cagr(cand)-cagr(f.qqq)})
    bm=next((r['bps'] for r in rows if r['excess_matched']<=0),None); bq=next((r['bps'] for r in rows if r['excess_qqq']<=0),None); by={r['bps']:r for r in rows}
    state='RECENT_CAUSAL_COST_CAPACITY_ABOVE_100BPS' if (bq is None or bq>100) and (bm is None or bm>100) else 'RECENT_CAUSAL_COST_CAPACITY_THIN'
    out={'schema':'research.p46_p36_causal_recent_cost_r1','parents':['P46','P36'],'scientific_contract':{'implementation':'fixed one-trading-day delayed entry','window':'2022-forward complete months','cost_grid_bps':'0..300 step 5','comparators':['exact matched blend','QQQ'],'no_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'months':len(f),'annual_turnover':float(f.turnover.mean()*12),'break_even_matched_bps':bm,'break_even_qqq_bps':bq,'at_50':by[50],'at_100':by[100],'decision':state}
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_causal_recent_cost_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
