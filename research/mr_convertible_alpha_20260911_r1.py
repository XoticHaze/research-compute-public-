from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T=['CWB','ICVT','SPY','HYG','BIL']; START='2015-06-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_convertible_alpha_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=px[T].resample('ME').last().pct_change(fill_method=None)

def alpha(sym,start,end=None):
    q=r.loc[start:end,[sym,'SPY','HYG','BIL']].dropna().copy()
    if len(q)<18:return {'months':int(len(q))}
    y=np.asarray(q[sym]-q.BIL,dtype=float).copy(); y[0]-=EP; y[-1]-=EP
    X=np.column_stack([np.ones(len(q)),np.asarray(q.SPY-q.BIL,dtype=float),np.asarray(q.HYG-q.BIL,dtype=float)])
    b=np.linalg.lstsq(X,y,rcond=None)[0]; resid=y-X@b
    return {'months':int(len(q)),'annualized_alpha_pp':float(1200*b[0]),'beta_spy':float(b[1]),'beta_hyg':float(b[2]),'resid_ann_vol':float(np.std(resid,ddof=1)*np.sqrt(12))}
windows={'2016+':('2016-01-01',None),'2018+':('2018-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2016_2018':('2016-01-01','2018-12-31'),'2019_2021':('2019-01-01','2021-12-31'),'2022_2024':('2022-01-01','2024-12-31'),'2025_plus':('2025-01-01',None)}
W={k:{s:alpha(s,*v) for s in ['CWB','ICVT']} for k,v in windows.items()}
B={k:{s:alpha(s,*v) for s in ['CWB','ICVT']} for k,v in blocks.items()}
posw={s:sum(W[k][s].get('annualized_alpha_pp',-999)>0 for k in W) for s in ['CWB','ICVT']}
posb={s:sum(B[k][s].get('annualized_alpha_pp',-999)>0 for k in B) for s in ['CWB','ICVT']}
coverage=all(B[k][s].get('months',0)>=18 for k in B for s in ['CWB','ICVT'])
passed=coverage and all(posw[s]>=3 and posb[s]>=3 and W['2022+'][s].get('annualized_alpha_pp',-999)>0 for s in ['CWB','ICVT'])
out={'schema':'research.mr_convertible_alpha_20260911_r1.v1','workload_id':'MR_CONVERTIBLE_ALPHA_20260911_R1','parent':'CONVERTIBLE_BOND_CONVEXITY_ALPHA','claim':'If convertible-bond structure contributes durable return beyond ordinary equity and high-yield credit exposure, both CWB and ICVT should retain positive after-cost annualized intercept after fixed SPY-BIL and HYG-BIL attribution across long windows and disjoint chronology.','contract':{'candidates':['CWB','ICVT'],'factors':['SPY_minus_BIL','HYG_minus_BIL'],'candidate_endpoint_cost_bps_each':25,'parameter_search':False,'windows':windows,'blocks':blocks,'minimum_block_months':18},'windows':W,'blocks':B,'positive_alpha_windows':posw,'positive_alpha_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both candidates have positive alpha in >=3/4 windows and >=3/4 blocks, positive 2022+ alpha, and each block has >=18 months. No factor/date/product rescue.','decision':('CONVERTIBLE_INDEPENDENT_ALPHA_SUPPORTED' if passed else ('CONVERTIBLE_ALPHA_COVERAGE_NOT_READY' if not coverage else 'CONVERTIBLE_INDEPENDENT_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'CWB_alpha_pp':{k:round(W[k]['CWB'].get('annualized_alpha_pp',-999),3) for k in W},'ICVT_alpha_pp':{k:round(W[k]['ICVT'].get('annualized_alpha_pp',-999),3) for k in W},'counts':{'CWB_positive_windows':posw['CWB'],'CWB_positive_blocks':posb['CWB'],'ICVT_positive_windows':posw['ICVT'],'ICVT_positive_blocks':posb['ICVT']}},sort_keys=True))
