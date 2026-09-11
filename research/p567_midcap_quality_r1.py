from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['XMHQ','MDY','SPY']
START='2011-01-01'; END='2026-09-12'; EP=.0025
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True); OUT=ART/'p567_midcap_quality_r1.json'
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None)

def stats(s):
    x=s.dropna().astype(float)
    if len(x)<12:return {'months':int(len(x))}
    y=x.to_numpy(float).copy(); y[0]-=EP; y[-1]-=EP
    w=np.cumprod(1+y); yrs=len(y)/12
    cagr=float(w[-1]**(1/yrs)-1); vol=float(np.std(y,ddof=1)*math.sqrt(12)); sh=float(np.mean(y)*12/vol) if vol>0 else None
    dd=float(np.min(w/np.maximum.accumulate(w)-1))
    return {'months':int(len(y)),'cagr':cagr,'vol':vol,'sharpe':sh,'max_drawdown':dd}

def frame(start,end=None):
    q=r.loc[start:end,T].dropna(); a=stats(q.XMHQ); m=stats(q.MDY); s=stats(q.SPY)
    return {'months':int(len(q)),'xmhq':a,'mdy':m,'spy':s,'xmhq_minus_mdy_pp':100*(a['cagr']-m['cagr']),'xmhq_minus_spy_pp':100*(a['cagr']-s['cagr'])}
windows={'2012+':frame('2012-01-01'),'2016+':frame('2016-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2012_2015':frame('2012-01-01','2015-12-31'),'2016_2019':frame('2016-01-01','2019-12-31'),'2020_2022':frame('2020-01-01','2022-12-31'),'2023_plus':frame('2023-01-01')}
posw=sum(v['months']>=24 and v['xmhq_minus_mdy_pp']>0 for v in windows.values()); posb=sum(v['months']>=24 and v['xmhq_minus_mdy_pp']>0 for v in blocks.values())
coverage=all(v['months']>=24 for v in blocks.values()); passed=coverage and posw>=3 and posb>=3 and windows['2022+']['xmhq_minus_mdy_pp']>0
out={'schema':'research.p567_midcap_quality_r1.v1','workload_id':'P567_MIDCAP_QUALITY_R1','parent':'MIDCAP_QUALITY_PROFITABILITY_TRANSPORT','claim':'Despite failed large-cap QUAL evidence, quality/profitability selection may be segment-conditional: XMHQ should deliver durable after-cost excess versus broad mid-cap MDY across fixed long windows and chronology; SPY is opportunity context only.','contract':{'endpoint_cost_bps_each':25,'matched_control':'MDY','opportunity_control':'SPY','windows':['2012+','2016+','2020+','2022+'],'blocks':['2012_2015','2016_2019','2020_2022','2023_plus'],'parameter_search':False},'windows':windows,'blocks':blocks,'positive_windows':int(posw),'positive_blocks':int(posb),'coverage_ready':coverage,'decision_rule':'SUPPORTED only if XMHQ has positive after-cost CAGR excess versus MDY in >=3/4 fixed windows and >=3/4 chronology blocks, is positive in 2022+, and every block has >=24 months. No alternate mid-cap quality fund/date/cost rescue.','decision':('MIDCAP_QUALITY_TRANSPORT_SUPPORTED' if passed else ('MIDCAP_QUALITY_SOURCE_COVERAGE_NOT_READY' if not coverage else 'MIDCAP_QUALITY_TRANSPORT_NOT_SUPPORTED')),'scientific_consequence':('Support quality/profitability as segment-conditional mid-cap transport despite prior large-cap QUAL failure; require attribution or independent implementation before broader family claims.' if passed else ('Record source coverage insufficiency only.' if not coverage else 'Reject this exact mid-cap quality transport without changing product/date/cost; preserve the prior large-cap QUAL failure and any positive subperiods separately.')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_windows':posw,'positive_blocks':posb,'windows_mdy_pp':{k:round(v['xmhq_minus_mdy_pp'],3) for k,v in windows.items()},'windows_spy_pp':{k:round(v['xmhq_minus_spy_pp'],3) for k,v in windows.items()}},sort_keys=True))
