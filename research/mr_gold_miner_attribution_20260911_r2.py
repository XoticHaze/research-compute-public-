from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T=['GDX','RING','GLD','SPY','BIL']; START='2012-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_gold_miner_attribution_20260911_r2.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=px[T].resample('ME').last().pct_change(fill_method=None)

def alpha(sym,start,end=None):
    q=r.loc[start:end,[sym,'GLD','SPY','BIL']].dropna().copy()
    if len(q)<18:return {'months':int(len(q))}
    y=np.asarray(q[sym]-q.BIL,dtype=float).copy(); y[0]-=EP; y[-1]-=EP
    X=np.column_stack([np.ones(len(q)),np.asarray(q.GLD-q.BIL,dtype=float),np.asarray(q.SPY-q.BIL,dtype=float)])
    b=np.linalg.lstsq(X,y,rcond=None)[0]; resid=y-X@b
    return {'months':int(len(q)),'annualized_alpha_pp':float(1200*b[0]),'beta_gld':float(b[1]),'beta_spy':float(b[2]),'resid_ann_vol':float(np.std(resid,ddof=1)*np.sqrt(12))}
windows={'2013+':('2013-01-01',None),'2016+':('2016-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2013_2015':('2013-01-01','2015-12-31'),'2016_2018':('2016-01-01','2018-12-31'),'2019_2021':('2019-01-01','2021-12-31'),'2022_2024':('2022-01-01','2024-12-31'),'2025_plus':('2025-01-01',None)}
W={k:{s:alpha(s,*v) for s in ['GDX','RING']} for k,v in windows.items()}
B={k:{s:alpha(s,*v) for s in ['GDX','RING']} for k,v in blocks.items()}
posw={s:sum(W[k][s].get('annualized_alpha_pp',-999)>0 for k in W) for s in ['GDX','RING']}
posb={s:sum(B[k][s].get('annualized_alpha_pp',-999)>0 for k in B) for s in ['GDX','RING']}
coverage=all(B[k][s].get('months',0)>=18 for k in B for s in ['GDX','RING'])
passed=coverage and all(posw[s]>=3 and posb[s]>=3 and W['2022+'][s].get('annualized_alpha_pp',-999)>0 for s in ['GDX','RING'])
out={'schema':'research.mr_gold_miner_attribution_20260911_r2.v1','workload_id':'MR_GOLD_MINER_ATTRIBUTION_20260911_R2','parent':'GOLD_MINER_OPERATING_LEVERAGE_ALPHA','claim':'If the supported miner-over-metal seam reflects independent miner-specific alpha rather than leveraged gold and broad-equity beta, both GDX and RING should retain positive after-cost annualized intercept after fixed GLD-BIL and SPY-BIL attribution across long windows and disjoint chronology.','contract':{'candidates':['GDX','RING'],'factors':['GLD_minus_BIL','SPY_minus_BIL'],'candidate_endpoint_cost_bps_each':25,'parameter_search':False,'windows':windows,'blocks':blocks,'minimum_block_months':18},'windows':W,'blocks':B,'positive_alpha_windows':posw,'positive_alpha_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both candidates have positive alpha in >=3/4 windows and >=3/5 blocks, positive 2022+ alpha, and each block has >=18 months. No factor/date/product rescue.','decision':('GOLD_MINER_INDEPENDENT_ALPHA_SUPPORTED' if passed else ('GOLD_MINER_ATTRIBUTION_COVERAGE_NOT_READY' if not coverage else 'GOLD_MINER_INDEPENDENT_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'GDX_alpha_pp':{k:round(W[k]['GDX'].get('annualized_alpha_pp',-999),3) for k in W},'RING_alpha_pp':{k:round(W[k]['RING'].get('annualized_alpha_pp',-999),3) for k in W},'counts':{'GDX_positive_windows':posw['GDX'],'GDX_positive_blocks':posb['GDX'],'RING_positive_windows':posw['RING'],'RING_positive_blocks':posb['RING']}},sort_keys=True))
