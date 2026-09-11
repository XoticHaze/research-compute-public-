from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T=['PAVE','XLI','IWM','BIL']; START='2018-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_pave_attribution_20260911_r2.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=px[T].resample('ME').last().pct_change(fill_method=None)

def alpha(start,end=None):
    q=r.loc[start:end,T].dropna().copy()
    if len(q)<18:return {'months':int(len(q))}
    y=np.array(q.PAVE-q.BIL,dtype=float,copy=True); y[0]-=EP; y[-1]-=EP
    X=np.column_stack([np.ones(len(q)),np.array(q.XLI-q.BIL,dtype=float,copy=True),np.array(q.IWM-q.BIL,dtype=float,copy=True)])
    b=np.linalg.lstsq(X,y,rcond=None)[0]; resid=y-X@b
    return {'months':int(len(q)),'annualized_alpha_pp':float(1200*b[0]),'beta_xli':float(b[1]),'beta_iwm':float(b[2]),'resid_ann_vol':float(np.std(resid,ddof=1)*np.sqrt(12))}
windows={'2019+':alpha('2019-01-01'),'2020+':alpha('2020-01-01'),'2022+':alpha('2022-01-01')}
blocks={'2019_2020':alpha('2019-01-01','2020-12-31'),'2021_2022':alpha('2021-01-01','2022-12-31'),'2023_plus':alpha('2023-01-01')}
posw=sum(v.get('months',0)>=18 and v.get('annualized_alpha_pp',-999)>0 for v in windows.values()); posb=sum(v.get('months',0)>=18 and v.get('annualized_alpha_pp',-999)>0 for v in blocks.values())
coverage=all(v.get('months',0)>=18 for v in blocks.values())
passed=coverage and posw>=2 and posb>=2 and windows['2022+'].get('annualized_alpha_pp',-999)>0
out={'schema':'research.mr_pave_attribution_20260911_r2.v1','workload_id':'MR_PAVE_ATTRIBUTION_20260911_R2','parent':'INFRASTRUCTURE_BUILDOUT_EQUITY_PREMIUM/PAVE_IMPLEMENTATION','claim':'If the PAVE implementation survivor reflects stock-selection/infrastructure alpha rather than industrial and size factor mix, PAVE should retain a positive after-cost annualized intercept after fixed XLI-BIL and IWM-BIL attribution across post-inception windows and disjoint chronology.','contract':{'candidate':'PAVE','factors':['XLI_minus_BIL','IWM_minus_BIL'],'candidate_endpoint_cost_bps_each':25,'minimum_block_months':18,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'positive_alpha_windows':posw,'positive_alpha_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if alpha is positive in >=2/3 windows and >=2/3 blocks, positive from 2022+, and each block has >=18 months. No factor/date/product rescue.','decision':('PAVE_IMPLEMENTATION_ALPHA_SUPPORTED' if passed else ('PAVE_ATTRIBUTION_COVERAGE_NOT_READY' if not coverage else 'PAVE_IMPLEMENTATION_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_windows':posw,'positive_blocks':posb,'window_alpha_pp':{k:round(v.get('annualized_alpha_pp',-999),3) for k,v in windows.items()},'block_alpha_pp':{k:round(v.get('annualized_alpha_pp',-999),3) for k,v in blocks.items()}},sort_keys=True))
