from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fixed_multifactor_cross_sectional_r1 as base
import p46_temporal_factor_discriminators_r1 as p46
import p46_p36_beta_residual_r1 as beta

def main():
 close=base.load(p46.SYMBOLS); ms=pd.Timestamp.now(tz='UTC').tz_localize(None).to_period('M').to_timestamp(); close=close.loc[close.index<ms]; a=p46.returns(close,p46.FACTORS); monthly=close.resample('ME').last(); q=monthly['QQQ'].pct_change().reindex(a.index); s=monthly['SPY'].pct_change().reindex(a.index); y=a.gross-a.turnover*.005-a.ew
 eras=[('2006_2011','2006-01-01','2012-01-01'),('2012_2016','2012-01-01','2017-01-01'),('2017_2021','2017-01-01','2022-01-01'),('2022_forward','2022-01-01','2100-01-01')]; tests={}
 for name,lo,hi in eras:
  ix=a.index[(a.index>=pd.Timestamp(lo))&(a.index<pd.Timestamp(hi))]; X=np.column_stack([q.loc[ix],s.loc[ix]]); r=beta.fit(y.loc[ix],X); r['bootstrap']=beta.boot(y.loc[ix],X,reps=4000,block=min(12,max(3,len(ix)//3)),seed=20260909+len(ix)); r['months']=len(ix); tests[name]=r
 pos=sum(v['annualized_intercept']>0 for v in tests.values()); ci=sum(v['bootstrap']['bootstrap_95pct'][0]>0 for v in tests.values()); state='P46_STANDALONE_RESIDUAL_NONOVERLAP_ERA_SUPPORTED' if pos>=3 and ci>=2 and tests['2022_forward']['annualized_intercept']>0 else 'P46_STANDALONE_RESIDUAL_NONOVERLAP_ERA_MIXED'; out={'schema':'research.p46_standalone_beta_residual_era_r1','parent':'P46','scientific_contract':{'active_return':'P46 net at 50 bps minus exact equal-weight universe control','factor_controls':['QQQ','SPY'],'eras':[x[0] for x in eras],'bootstrap':'4000 moving blocks within era','no_parameter_or_weight_tuning':True},'source':{'normalized_complete_month_price_panel_sha256':base.source_hash(close)},'tests':tests,'positive_intercept_eras':pos,'positive_95pct_lower_bound_eras':ci,'decision':state}; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p46_standalone_beta_residual_era_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
if __name__=='__main__': main()
