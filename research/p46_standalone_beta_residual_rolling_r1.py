from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
import p46_p36_beta_residual_r1 as beta

def main():
    close=base.load(p46.SYMBOLS); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]
    a=p46.returns(close,p46.FACTORS); monthly=close.resample('ME').last(); q=monthly['QQQ'].pct_change().reindex(a.index); s=monthly['SPY'].pct_change().reindex(a.index); y=a.gross-a.turnover*.005-a.ew
    tests={}
    for w in (36,60):
      vals=[]
      for end in range(w,len(a)+1):
        ix=a.index[end-w:end]; r=beta.fit(y.loc[ix],np.column_stack([q.loc[ix],s.loc[ix]])); vals.append(r['annualized_intercept'])
      z=pd.Series(vals,dtype=float); tests[str(w)]={'windows':len(z),'positive_fraction':float((z>0).mean()),'median_annualized_intercept':float(z.median()),'p10_annualized_intercept':float(z.quantile(.1)),'worst_annualized_intercept':float(z.min()),'recent_annualized_intercept':float(z.iloc[-1])}
    state='P46_STANDALONE_RESIDUAL_ROLLING_SUPPORTED' if tests['36']['positive_fraction']>=.7 and tests['60']['positive_fraction']>=.8 and tests['60']['p10_annualized_intercept']>0 else 'P46_STANDALONE_RESIDUAL_ROLLING_MIXED'
    out={'schema':'research.p46_standalone_beta_residual_rolling_r1','parent':'P46','scientific_contract':{'candidate':'fixed P46 top-2 four-factor cross-asset selector','active_return':'P46 net at 50 bps minus exact equal-weight universe control','factor_controls':['QQQ','SPY'],'rolling_windows_months':[36,60],'no_parameter_or_weight_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_standalone_beta_residual_rolling_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
