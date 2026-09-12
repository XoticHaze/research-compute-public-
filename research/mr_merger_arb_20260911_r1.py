from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T=['MNA','SPY','HYG','BIL']; START='2010-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_merger_arb_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=px[T].resample('ME').last().pct_change(fill_method=None)

def alpha(start,end=None):
    q=r.loc[start:end,T].dropna().copy()
    if len(q)<24:return {'months':int(len(q))}
    y=np.array(q['MNA']-q['BIL'],dtype=float,copy=True); y[0]-=EP; y[-1]-=EP
    X=np.column_stack([np.ones(len(q)),np.array(q['SPY']-q['BIL'],dtype=float,copy=True),np.array(q['HYG']-q['BIL'],dtype=float,copy=True)])
    b=np.linalg.lstsq(X,y,rcond=None)[0]; resid=y-X@b
    return {'months':int(len(q)),'annualized_alpha_pp':float(1200*b[0]),'beta_spy':float(b[1]),'beta_hyg':float(b[2]),'resid_ann_vol':float(np.std(resid,ddof=1)*np.sqrt(12))}

def cagr(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252:return None
    years=(s.index[-1]-s.index[0]).days/365.2425
    gross=(float(s.iloc[-1])/float(s.iloc[0]))*((1-EP)**2 if sym=='MNA' else 1.0)
    return gross**(1/years)-1

def frame(start,end=None):
    a=alpha(start,end); a['MNA_cagr']=cagr('MNA',start,end); a['BIL_cagr']=cagr('BIL',start,end); a['SPY_cagr']=cagr('SPY',start,end)
    if a['MNA_cagr'] is not None and a['BIL_cagr'] is not None:a['MNA_minus_BIL_cagr_pp']=100*(a['MNA_cagr']-a['BIL_cagr'])
    return a
windows={'2011+':frame('2011-01-01'),'2015+':frame('2015-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2011_2014':frame('2011-01-01','2014-12-31'),'2015_2019':frame('2015-01-01','2019-12-31'),'2020_2022':frame('2020-01-01','2022-12-31'),'2023_plus':frame('2023-01-01')}
posw=sum(v.get('annualized_alpha_pp',-999)>0 for v in windows.values()); posb=sum(v.get('annualized_alpha_pp',-999)>0 for v in blocks.values())
coverage=all(v.get('months',0)>=24 for v in blocks.values())
passed=coverage and posw>=3 and posb>=3 and windows['2022+'].get('annualized_alpha_pp',-999)>0 and windows['2022+'].get('MNA_minus_BIL_cagr_pp',-999)>0
out={'schema':'research.mr_merger_arb_20260911_r1.v1','workload_id':'MR_MERGER_ARB_20260911_R1','parent':'MERGER_ARBITRAGE_EVENT_DRIVEN_ALPHA','claim':'If merger-arbitrage/event-driven returns contain durable alpha beyond broad equity and high-yield credit beta, MNA should retain a positive after-cost annualized intercept versus SPY-BIL and HYG-BIL across fixed long windows and disjoint chronology while remaining positive versus BIL recently.','contract':{'candidate':'MNA','factors':['SPY_minus_BIL','HYG_minus_BIL'],'cash_control':'BIL','candidate_endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'positive_alpha_windows':posw,'positive_alpha_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if alpha is positive in >=3/4 windows and >=3/4 disjoint blocks, 2022+ alpha is positive, 2022+ MNA-BIL CAGR excess is positive, and each block has >=24 months. No factor/date/product rescue.','decision':('MERGER_ARB_ALPHA_SUPPORTED' if passed else ('MERGER_ARB_SOURCE_COVERAGE_NOT_READY' if not coverage else 'MERGER_ARB_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_windows':posw,'positive_blocks':posb,'window_alpha_pp':{k:round(v.get('annualized_alpha_pp',-999),3) for k,v in windows.items()},'window_bil_excess_pp':{k:round(v.get('MNA_minus_BIL_cagr_pp',-999),3) for k,v in windows.items()}},sort_keys=True))
