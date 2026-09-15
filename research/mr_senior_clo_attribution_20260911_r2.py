from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T=['JAAA','FLRN','HYG','BIL']; START='2020-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_senior_clo_attribution_20260911_r2.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=px[T].resample('ME').last().pct_change(fill_method=None)

def alpha(start,end=None):
    q=r.loc[start:end,T].dropna().copy()
    if len(q)<18:return {'months':int(len(q))}
    y=np.array(q.JAAA-q.BIL,dtype=float,copy=True); y[0]-=EP; y[-1]-=EP
    X=np.column_stack([np.ones(len(q)),np.array(q.FLRN-q.BIL,dtype=float,copy=True),np.array(q.HYG-q.BIL,dtype=float,copy=True)])
    b=np.linalg.lstsq(X,y,rcond=None)[0]; resid=y-X@b
    return {'months':int(len(q)),'annualized_alpha_pp':float(1200*b[0]),'beta_flrn':float(b[1]),'beta_hyg':float(b[2]),'resid_ann_vol':float(np.std(resid,ddof=1)*np.sqrt(12))}

windows={'2021+':alpha('2021-01-01'),'2022+':alpha('2022-01-01'),'2023+':alpha('2023-01-01')}
blocks={'2021_2022':alpha('2021-01-01','2022-12-31'),'2023_2024':alpha('2023-01-01','2024-12-31'),'2025_plus':alpha('2025-01-01')}
posw=sum(v.get('months',0)>=18 and v.get('annualized_alpha_pp',-999)>0 for v in windows.values())
posb=sum(v.get('months',0)>=18 and v.get('annualized_alpha_pp',-999)>0 for v in blocks.values())
coverage=all(v.get('months',0)>=18 for v in blocks.values())
passed=coverage and posw>=2 and posb>=2 and windows['2023+'].get('annualized_alpha_pp',-999)>0
out={'schema':'research.mr_senior_clo_attribution_20260911_r2.v1','workload_id':'MR_SENIOR_CLO_ATTRIBUTION_20260911_R2','parent':'SENIOR_CLO_CARRY_ALPHA','claim':'If the senior-CLO survivor reflects structured-credit alpha beyond ordinary floating-rate IG and high-yield credit beta, JAAA should retain a positive after-cost annualized intercept after fixed FLRN-BIL and HYG-BIL attribution across post-inception long windows and disjoint chronology.','contract':{'candidate':'JAAA','factors':['FLRN_minus_BIL','HYG_minus_BIL'],'candidate_endpoint_cost_bps_each':25,'minimum_block_months':18,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'positive_alpha_windows':posw,'positive_alpha_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if alpha is positive in >=2/3 windows and >=2/3 blocks, positive from 2023+, and each block has >=18 months. No factor/date/product rescue.','decision':('SENIOR_CLO_INDEPENDENT_ALPHA_SUPPORTED' if passed else ('SENIOR_CLO_ATTRIBUTION_COVERAGE_NOT_READY' if not coverage else 'SENIOR_CLO_INDEPENDENT_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_windows':posw,'positive_blocks':posb,'window_alpha_pp':{k:round(v.get('annualized_alpha_pp',-999),3) for k,v in windows.items()},'block_alpha_pp':{k:round(v.get('annualized_alpha_pp',-999),3) for k,v in blocks.items()}},sort_keys=True))
