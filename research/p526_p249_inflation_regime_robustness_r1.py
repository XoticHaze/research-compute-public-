from __future__ import annotations
import json,runpy
from pathlib import Path
import pandas as pd

OUT=Path('research/artifacts/p526_p249_inflation_regime_robustness_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
# Exact P523 P249 reconstruction; P526 changes no weights, products, costs, or model rules.
ns=runpy.run_path('research/p523_p249_semiconductor_dependency_r1.py',run_name='p523_reconstruct')
q=ns['q'].copy()
# Reuse the exact P518 causal macro state: trailing 6m CPI growth > preceding 6m growth,
# with a conservative two-month lag before applying the state to the holding month.
cpi=pd.read_csv('https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL')
dc='DATE' if 'DATE' in cpi.columns else ('observation_date' if 'observation_date' in cpi.columns else cpi.columns[0])
cpi[dc]=pd.to_datetime(cpi[dc]); cpi['CPIAUCSL']=pd.to_numeric(cpi['CPIAUCSL'],errors='coerce'); cpi=cpi.dropna().set_index(dc)['CPIAUCSL'].resample('ME').last()
g6=cpi.pct_change(6); accel=(g6>g6.shift(6)).astype(float).shift(2).rename('inflation_accel')
q=q.join(accel,how='inner').dropna(subset=['inflation_accel'])

def stats(flag):
    z=q[q.inflation_accel==flag]
    if len(z)<24: return {'ready':False,'months':int(len(z))}
    ex=z.p249-z.ctl; vs=z.p249-z.spy; down=z[z.spy<0]
    return {'ready':True,'months':int(len(z)),'annualized_mean_excess_vs_matched':float(ex.mean()*12),'annualized_mean_excess_vs_spy':float(vs.mean()*12),'matched_excess_hit_rate':float((ex>0).mean()),'down_spy_months':int(len(down)),'down_spy_annualized_mean_excess_vs_matched':float((down.p249-down.ctl).mean()*12) if len(down) else None}

states={'ACCELERATING':stats(1.0),'NON_ACCELERATING':stats(0.0)}
ready=all(v.get('ready') for v in states.values())
supported=ready and all(v['annualized_mean_excess_vs_matched']>0 for v in states.values()) and all(v['annualized_mean_excess_vs_spy']>0 for v in states.values())
decision='P249_INFLATION_REGIME_ROBUSTNESS_SUPPORTED' if supported else ('P249_INFLATION_REGIME_DEPENDENCY_DETECTED' if ready else 'P249_INFLATION_REGIME_DATA_NOT_READY')
out={'schema':'research.p526_p249_inflation_regime_robustness_r1.v1','workload_id':'P526_P249_INFLATION_REGIME_ROBUSTNESS_R1','parent':'P249','source_identity':{'p523_head_sha':'963d15bfef9c414bfda51a6004d23e768baf7f9c','p523_run_id':34556336625,'macro_state':'P518 fixed CPI acceleration with two-month lag'},'claim':'P249 should retain positive matched excess and broad-market opportunity value in both the previously frozen accelerating and non-accelerating inflation states.','contract':{'minimum_months_per_state':24,'support_rule':'annualized mean excess versus matched control >0 and versus SPY >0 in both states','no_macro_signal_lag_threshold_state_weight_product_date_cost_or_subset_search':True},'states':states,'decision':decision,'scientific_consequence':'Use this only to narrow or strengthen P249 regime robustness. Do not apply a macro overlay, change weights, or create an allocation consequence from the diagnostic.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'states':states},sort_keys=True))