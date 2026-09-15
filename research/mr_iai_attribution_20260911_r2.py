from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T=['IAI','XLF','QQQ','BIL']; START='2009-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_iai_attribution_20260911_r2.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=px[T].resample('ME').last().pct_change(fill_method=None)

def alpha(start,end=None):
    q=r.loc[start:end,T].dropna().copy()
    if len(q)<24:return {'months':int(len(q))}
    y=np.array(q.IAI-q.BIL,dtype=float,copy=True); y[0]-=EP; y[-1]-=EP
    X=np.column_stack([np.ones(len(q)),np.array(q.XLF-q.BIL,dtype=float,copy=True),np.array(q.QQQ-q.BIL,dtype=float,copy=True)])
    b=np.linalg.lstsq(X,y,rcond=None)[0]; resid=y-X@b
    return {'months':int(len(q)),'annualized_alpha_pp':float(1200*b[0]),'beta_xlf':float(b[1]),'beta_qqq':float(b[2]),'resid_ann_vol':float(np.std(resid,ddof=1)*np.sqrt(12))}
windows={'2010+':alpha('2010-01-01'),'2015+':alpha('2015-01-01'),'2020+':alpha('2020-01-01'),'2022+':alpha('2022-01-01')}
blocks={'2010_2013':alpha('2010-01-01','2013-12-31'),'2014_2017':alpha('2014-01-01','2017-12-31'),'2018_2021':alpha('2018-01-01','2021-12-31'),'2022_plus':alpha('2022-01-01')}
posw=sum(v.get('months',0)>=24 and v.get('annualized_alpha_pp',-999)>0 for v in windows.values()); posb=sum(v.get('months',0)>=24 and v.get('annualized_alpha_pp',-999)>0 for v in blocks.values())
coverage=all(v.get('months',0)>=24 for v in blocks.values())
passed=coverage and posw>=3 and posb>=3 and windows['2022+'].get('annualized_alpha_pp',-999)>0
out={'schema':'research.mr_iai_attribution_20260911_r2.v1','workload_id':'MR_IAI_ATTRIBUTION_20260911_R2','parent':'CAPITAL_MARKETS_SPECIALIZATION_PREMIUM/IAI_IMPLEMENTATION','claim':'If the IAI implementation survivor reflects capital-markets selection alpha rather than broad financial plus growth/market-structure beta, IAI should retain a positive after-cost annualized intercept after fixed XLF-BIL and QQQ-BIL attribution across long windows and disjoint chronology.','contract':{'candidate':'IAI','factors':['XLF_minus_BIL','QQQ_minus_BIL'],'candidate_endpoint_cost_bps_each':25,'minimum_block_months':24,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'positive_alpha_windows':posw,'positive_alpha_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if alpha is positive in >=3/4 windows and >=3/4 blocks, positive from 2022+, and each block has >=24 months. No factor/date/product rescue.','decision':('IAI_IMPLEMENTATION_ALPHA_SUPPORTED' if passed else ('IAI_ATTRIBUTION_COVERAGE_NOT_READY' if not coverage else 'IAI_IMPLEMENTATION_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_windows':posw,'positive_blocks':posb,'window_alpha_pp':{k:round(v.get('annualized_alpha_pp',-999),3) for k,v in windows.items()},'block_alpha_pp':{k:round(v.get('annualized_alpha_pp',-999),3) for k,v in blocks.items()}},sort_keys=True))
