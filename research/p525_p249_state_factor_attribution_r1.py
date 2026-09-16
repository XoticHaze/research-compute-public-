from __future__ import annotations
import json,runpy
from pathlib import Path
import numpy as np
import pandas as pd

OUT=Path('research/artifacts/p525_p249_state_factor_attribution_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
# Reuse exact P523 reconstruction and causal P36 states from the parent branch.
ns=runpy.run_path('research/p523_p249_semiconductor_dependency_r1.py',run_name='p523_reconstruct')
q=ns['q'].copy(); r=ns['r']
# Align monthly P249 returns to SPY and the state-specific selected P36 asset.
q=q.join(r[['QQQ','SOXX']],how='left')

def attrib(state,asset):
    z=q[q.state==state][['p249','spy',asset]].dropna()
    if len(z)<24: return {'ready':False,'months':int(len(z))}
    y=z.p249.to_numpy(); X=np.column_stack([np.ones(len(z)),z.spy.to_numpy(),z[asset].to_numpy()])
    beta=np.linalg.lstsq(X,y,rcond=None)[0]; fitted=X@beta; resid=y-fitted
    return {'ready':True,'months':int(len(z)),'annualized_alpha':float(beta[0]*12),'spy_beta':float(beta[1]),'selected_asset_beta':float(beta[2]),'residual_vol_annualized':float(np.std(resid,ddof=1)*np.sqrt(12)),'positive_residual_month_rate':float((resid>0).mean())}

states={'SOXX':attrib('SOXX','SOXX'),'QQQ':attrib('QQQ','QQQ')}
ready=all(v.get('ready') for v in states.values())
supported=ready and all(v['annualized_alpha']>0 for v in states.values())
decision='P249_STATE_RESIDUAL_ALPHA_BROADLY_SUPPORTED' if supported else ('P249_STATE_RESIDUAL_ALPHA_CONCENTRATED' if ready else 'P249_STATE_FACTOR_ATTRIBUTION_NOT_READY')
out={'schema':'research.p525_p249_state_factor_attribution_r1.v1','workload_id':'P525_P249_STATE_FACTOR_ATTRIBUTION_R1','parent':'P249','source_identity':{'p523_head_sha':'963d15bfef9c414bfda51a6004d23e768baf7f9c','p523_run_id':34556336625},'claim':'P249 should retain positive monthly residual alpha in both causal P36 states after controlling for broad-market SPY and the state-selected P36 asset, rather than its matched excess being explained by semiconductor or mega-cap beta.','contract':{'states':{'SOXX':'OLS P249 ~ 1 + SPY + SOXX in months P36 selected SOXX','QQQ':'OLS P249 ~ 1 + SPY + QQQ in months P36 selected QQQ'},'minimum_months_per_state':24,'support_rule':'annualized OLS intercept >0 in both states','no_state_threshold_asset_factor_window_weight_or_subset_search':True},'states':states,'decision':decision,'scientific_consequence':'Use this attribution to narrow or strengthen the P249 survivor claim only. Do not change P249 weights, primitives, allocation, runtime, or broker authority from a factor-attribution diagnostic.','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps({'decision':decision,'states':states},sort_keys=True))