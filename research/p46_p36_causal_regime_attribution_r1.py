from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_p36_causal_temporal_holdout_r1 as causal

def pack(f):
    x=f.candidate-f.matched
    return {'months':len(f),'mean_monthly_excess':float(x.mean()),'annualized_mean_excess':float(x.mean()*12),'candidate_cagr':causal.cagr(f.candidate),'matched_cagr':causal.cagr(f.matched)}
def main():
    close=base.load(causal.ALL); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]
    f=causal.build(close,50,1).copy(); monthly_spy=close['SPY'].resample('ME').last(); trend=monthly_spy/monthly_spy.rolling(10,min_periods=10).mean()-1
    f['signal_month']=pd.DatetimeIndex(f.index).to_period('M').to_timestamp('M')-pd.offsets.MonthEnd(1)
    f['risk_on']=[bool(trend.asof(d)>=0) if not pd.isna(trend.asof(d)) else False for d in f['signal_month']]
    on=f[f.risk_on]; off=f[~f.risk_on]; out={'schema':'research.p46_p36_causal_regime_attribution_r1','parents':['P46','P36'],'scientific_contract':{'implementation':'fixed one-trading-day delayed entry at 50 bps','regime':'prior completed SPY month-end above/below trailing 10-month SMA','regime_information':'prior/completed only','comparator':'exact matched blend within same months','no_regime_gate_or_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'risk_on':pack(on),'risk_off':pack(off)}
    out['decision']='CAUSAL_RISK_OFF_WEAKNESS_PERSISTS' if out['risk_off']['annualized_mean_excess']<=0 else 'CAUSAL_EDGE_POSITIVE_BOTH_REGIMES'
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_p36_causal_regime_attribution_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
