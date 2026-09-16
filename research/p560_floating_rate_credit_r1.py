from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['FLRN','FLOT','SHV','BIL','SPY']
START='2012-01-01'; END='2026-09-12'; EP=.0025
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True); OUT=ART/'p560_floating_rate_credit_r1.json'
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
    shv=stats(q.SHV); out={'months':int(len(q)),'shv':shv,'bil':stats(q.BIL),'spy':stats(q.SPY)}
    for sym in ['FLRN','FLOT']:
        s=stats(q[sym]); out[sym.lower()]=s; out[sym.lower()+'_minus_shv_pp']=100*(s['cagr']-shv['cagr'])
    return out
windows={'2013+':frame('2013-01-01'),'2018+':frame('2018-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2013_2016':frame('2013-01-01','2016-12-31'),'2017_2020':frame('2017-01-01','2020-12-31'),'2021_2023':frame('2021-01-01','2023-12-31'),'2024_plus':frame('2024-01-01')}
def counts(sym):
    k=sym.lower()+'_minus_shv_pp'; return (sum(v['months']>=24 and v[k]>0 for v in windows.values()),sum(v['months']>=18 and v[k]>0 for v in blocks.values()))
fw,fb=counts('FLRN'); tw,tb=counts('FLOT'); coverage=all(v['months']>=18 for v in blocks.values())
recent_ok=windows['2022+']['flrn_minus_shv_pp']>0 and windows['2022+']['flot_minus_shv_pp']>0
passed=coverage and fw>=3 and fb>=3 and tw>=3 and tb>=3 and recent_ok
out={'schema':'research.p560_floating_rate_credit_r1.v1','workload_id':'P560_FLOATING_RATE_CREDIT_R1','parent':'FLOATING_RATE_IG_CREDIT_CARRY','claim':'Investment-grade floating-rate credit should deliver durable after-cost excess versus ultra-short Treasury SHV across two independent fund implementations without relying on duration; BIL/SPY are opportunity context only.','contract':{'endpoint_cost_bps_each':25,'implementations':['FLRN','FLOT'],'matched_control':'SHV','windows':['2013+','2018+','2020+','2022+'],'blocks':['2013_2016','2017_2020','2021_2023','2024_plus'],'parameter_search':False},'windows':windows,'blocks':blocks,'counts':{'FLRN_positive_windows':fw,'FLRN_positive_blocks':fb,'FLOT_positive_windows':tw,'FLOT_positive_blocks':tb},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both FLRN and FLOT have positive after-cost CAGR excess versus SHV in >=3/4 fixed windows and >=3/4 chronology blocks, both are positive in 2022+, and all blocks have >=18 common months. No alternate fund/control/date/cost rescue.','decision':('FLOATING_RATE_IG_CREDIT_CARRY_SUPPORTED' if passed else ('FLOATING_RATE_IG_CREDIT_SOURCE_COVERAGE_NOT_READY' if not coverage else 'FLOATING_RATE_IG_CREDIT_CARRY_NOT_SUPPORTED')),'scientific_consequence':('Support a cross-implementation floating-rate IG credit carry family; next test must adjudicate credit-beta/drawdown compensation before calling the excess independent alpha.' if passed else ('Record source coverage insufficiency only.' if not coverage else 'Reject this exact broad floating-rate IG carry claim without substituting products/controls; preserve any passing subperiods as regime evidence only.')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'flrn_windows_pp':{k:round(v['flrn_minus_shv_pp'],3) for k,v in windows.items()},'flot_windows_pp':{k:round(v['flot_minus_shv_pp'],3) for k,v in windows.items()}},sort_keys=True))
