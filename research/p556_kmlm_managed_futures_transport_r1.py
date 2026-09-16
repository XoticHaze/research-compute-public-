from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['KMLM','DBMF','BIL','SPY']
START='2020-01-01'; END='2026-09-12'; EP=.0025
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True); OUT=ART/'p556_kmlm_managed_futures_transport_r1.json'
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None)

def stats(s):
    x=s.dropna().astype(float)
    if len(x)<12:return {'months':int(len(x))}
    y=x.to_numpy().copy(); y[0]-=EP; y[-1]-=EP
    w=np.cumprod(1+y); yrs=len(y)/12
    cagr=float(w[-1]**(1/yrs)-1); vol=float(np.std(y,ddof=1)*math.sqrt(12)); sh=float(np.mean(y)*12/vol) if vol>0 else None
    dd=float(np.min(w/np.maximum.accumulate(w)-1))
    return {'months':int(len(y)),'cagr':cagr,'vol':vol,'sharpe':sh,'max_drawdown':dd}

def frame(start,end=None):
    q=r.loc[start:end,T].dropna()
    a=stats(q.KMLM); cash=stats(q.BIL); db=stats(q.DBMF); sp=stats(q.SPY)
    kres=q.KMLM-q.BIL; dres=q.DBMF-q.BIL
    corr=float(kres.corr(dres)) if len(q)>=12 else None
    return {'months':int(len(q)),'kmlm':a,'bil':cash,'dbmf':db,'spy':sp,'kmlm_bil_excess_pp':100*(a['cagr']-cash['cagr']),'kmlm_spy_opportunity_pp':100*(a['cagr']-sp['cagr']),'kmlm_dbmf_residual_corr':corr}
windows={'2021+':frame('2021-01-01'),'2022+':frame('2022-01-01'),'2023+':frame('2023-01-01')}
blocks={'2021_2022':frame('2021-01-01','2022-12-31'),'2023_2024':frame('2023-01-01','2024-12-31'),'2025_plus':frame('2025-01-01')}
posw=sum(v['months']>=18 and v['kmlm_bil_excess_pp']>0 for v in windows.values())
posb=sum(v['months']>=18 and v['kmlm_bil_excess_pp']>0 for v in blocks.values())
full=windows['2021+']; corr=full['kmlm_dbmf_residual_corr']
coverage=all(v['months']>=18 for v in blocks.values())
passed=coverage and posw>=2 and posb>=2 and full['kmlm']['sharpe'] is not None and full['kmlm']['sharpe']>0 and corr is not None and abs(corr)<=0.75
out={'schema':'research.p556_kmlm_managed_futures_transport_r1.v1','workload_id':'P556_KMLM_MANAGED_FUTURES_TRANSPORT_R1','parent':'MANAGED_FUTURES_RETURN_SOURCE_TRANSPORT','claim':'A distinct KMLM managed-futures implementation should earn durable after-cost excess over BIL and not collapse into the same residual return stream as DBMF; SPY is opportunity context only.','contract':{'endpoint_cost_bps_each':25,'windows':['2021+','2022+','2023+'],'blocks':['2021_2022','2023_2024','2025_plus'],'max_abs_residual_corr_to_dbmf':0.75,'parameter_search':False},'windows':windows,'blocks':blocks,'positive_windows':int(posw),'positive_blocks':int(posb),'coverage_ready':coverage,'decision_rule':'SUPPORTED only if all three blocks have >=18 common months, >=2/3 windows and >=2/3 blocks show positive KMLM-BIL after-cost CAGR excess, full-history KMLM Sharpe >0, and abs(KMLM-BIL vs DBMF-BIL residual correlation)<=0.75. No alternate manager/date/cost/correlation rescue.','decision':('MANAGED_FUTURES_TRANSPORT_SUPPORTED' if passed else ('MANAGED_FUTURES_TRANSPORT_SOURCE_COVERAGE_NOT_READY' if not coverage else 'MANAGED_FUTURES_TRANSPORT_NOT_SUPPORTED')),'scientific_consequence':('Strengthen managed-futures as a cross-implementation diversifying return-source family; DBMF-specific evidence remains separate and portfolio authority stays with Coordinator.' if passed else ('Record source-coverage insufficiency only; do not infer model failure.' if not coverage else 'Reject broad transport from DBMF to this exact KMLM implementation while preserving DBMF-specific survivor evidence.')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_windows':posw,'positive_blocks':posb,'full_excess_pp':round(full['kmlm_bil_excess_pp'],3),'residual_corr':None if corr is None else round(corr,3),'blocks_pp':{k:round(v['kmlm_bil_excess_pp'],3) for k,v in blocks.items()}},sort_keys=True))
