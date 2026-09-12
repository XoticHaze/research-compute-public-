from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T=['SPLV','USMV','SPY','BIL']; START='2011-10-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_low_vol_alpha_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=px[T].resample('ME').last().pct_change(fill_method=None)

def alpha(sym,start,end=None):
    q=r.loc[start:end,[sym,'SPY','BIL']].dropna().copy()
    if len(q)<24:return {'months':int(len(q))}
    y=np.asarray(q[sym]-q.BIL,dtype=float).copy(); y[0]-=EP; y[-1]-=EP
    x=np.asarray(q.SPY-q.BIL,dtype=float).copy()
    X=np.column_stack([np.ones(len(q)),x]); b=np.linalg.lstsq(X,y,rcond=None)[0]
    resid=y-X@b
    wealth=(1+pd.Series(y,index=q.index)).cumprod(); dd=float((wealth/wealth.cummax()-1).min())
    return {'months':int(len(q)),'annualized_alpha_pp':float(1200*b[0]),'beta_spy':float(b[1]),'resid_ann_vol':float(np.std(resid,ddof=1)*np.sqrt(12)),'max_drawdown_excess_wealth':dd}

windows={'2012+':('2012-01-01',None),'2015+':('2015-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2012_2014':('2012-01-01','2014-12-31'),'2015_2017':('2015-01-01','2017-12-31'),'2018_2020':('2018-01-01','2020-12-31'),'2021_2023':('2021-01-01','2023-12-31'),'2024_plus':('2024-01-01',None)}
W={k:{s:alpha(s,*v) for s in ['SPLV','USMV']} for k,v in windows.items()}
B={k:{s:alpha(s,*v) for s in ['SPLV','USMV']} for k,v in blocks.items()}
posw={s:sum(W[k][s].get('annualized_alpha_pp',-999)>0 for k in W) for s in ['SPLV','USMV']}
posb={s:sum(B[k][s].get('annualized_alpha_pp',-999)>0 for k in B) for s in ['SPLV','USMV']}
coverage=all(B[k][s].get('months',0)>=24 for k in B for s in ['SPLV','USMV'])
passed=coverage and all(posw[s]>=3 and posb[s]>=3 and W['2022+'][s].get('annualized_alpha_pp',-999)>0 for s in ['SPLV','USMV'])
out={'schema':'research.mr_low_vol_alpha_20260911_r1.v1','workload_id':'MR_LOW_VOL_ALPHA_20260911_R1','parent':'LOW_VOLATILITY_ANOMALY','claim':'If the low-volatility anomaly is durable rather than merely lower market beta, both SPLV and USMV should retain positive after-cost annualized alpha after fixed SPY-BIL beta attribution across long windows and disjoint chronology.','contract':{'candidates':['SPLV','USMV'],'market_factor':'SPY_minus_BIL','candidate_endpoint_cost_bps_each':25,'parameter_search':False,'windows':windows,'blocks':blocks},'windows':W,'blocks':B,'positive_alpha_windows':posw,'positive_alpha_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both candidates have positive alpha in >=3/4 windows and >=3/5 blocks, positive 2022+ alpha, and each block has >=24 months. No factor/date/product rescue.','decision':('LOW_VOLATILITY_ALPHA_SUPPORTED' if passed else ('LOW_VOLATILITY_COVERAGE_NOT_READY' if not coverage else 'LOW_VOLATILITY_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'SPLV_alpha_pp':{k:round(W[k]['SPLV'].get('annualized_alpha_pp',-999),3) for k in W},'USMV_alpha_pp':{k:round(W[k]['USMV'].get('annualized_alpha_pp',-999),3) for k in W},'counts':{'SPLV_positive_windows':posw['SPLV'],'SPLV_positive_blocks':posb['SPLV'],'USMV_positive_windows':posw['USMV'],'USMV_positive_blocks':posb['USMV']}},sort_keys=True))
