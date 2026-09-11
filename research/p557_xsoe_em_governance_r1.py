from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['XSOE','VWO','SPY','BIL']
START='2014-01-01'; END='2026-09-12'; EP=.0025
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True); OUT=ART/'p557_xsoe_em_governance_r1.json'
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
    a=stats(q.XSOE); b=stats(q.VWO); s=stats(q.SPY)
    return {'months':int(len(q)),'xsoe':a,'vwo':b,'spy':s,'matched_excess_pp':100*(a['cagr']-b['cagr']),'spy_opportunity_pp':100*(a['cagr']-s['cagr'])}
windows={'2015+':frame('2015-01-01'),'2018+':frame('2018-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2015_2017':frame('2015-01-01','2017-12-31'),'2018_2020':frame('2018-01-01','2020-12-31'),'2021_2023':frame('2021-01-01','2023-12-31'),'2024_plus':frame('2024-01-01')}
posw=sum(v['months']>=24 and v['matched_excess_pp']>0 for v in windows.values())
posb=sum(v['months']>=18 and v['matched_excess_pp']>0 for v in blocks.values())
coverage=all(v['months']>=18 for v in blocks.values())
passed=coverage and posw>=3 and posb>=3 and windows['2020+']['matched_excess_pp']>0
out={'schema':'research.p557_xsoe_em_governance_r1.v1','workload_id':'P557_XSOE_EM_GOVERNANCE_R1','parent':'EMERGING_MARKET_GOVERNANCE_SELECTION','claim':'Excluding state-owned enterprises via XSOE should deliver durable after-cost excess versus broad EM VWO across fixed windows/chronology; SPY is opportunity context only.','contract':{'endpoint_cost_bps_each':25,'windows':['2015+','2018+','2020+','2022+'],'blocks':['2015_2017','2018_2020','2021_2023','2024_plus'],'parameter_search':False},'windows':windows,'blocks':blocks,'positive_windows':int(posw),'positive_blocks':int(posb),'coverage_ready':coverage,'decision_rule':'SUPPORTED only if all blocks have >=18 common months, >=3/4 long windows and >=3/4 chronology blocks have positive XSOE-VWO after-cost CAGR excess, and 2020+ is positive. No alternate product/date/cost rescue.','decision':('EM_GOVERNANCE_SELECTION_SUPPORTED' if passed else ('EM_GOVERNANCE_SELECTION_SOURCE_COVERAGE_NOT_READY' if not coverage else 'EM_GOVERNANCE_SELECTION_NOT_SUPPORTED')),'scientific_consequence':('Treat EM ex-state-owned governance selection as a scoped survivor requiring independent implementation/fundamental attribution before broader promotion.' if passed else ('Record source coverage insufficiency only.' if not coverage else 'Reject this exact durable XSOE governance-selection claim without substituting another fund or moving dates.')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_windows':posw,'positive_blocks':posb,'windows_pp':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()},'blocks_pp':{k:round(v['matched_excess_pp'],3) for k,v in blocks.items()}},sort_keys=True))
