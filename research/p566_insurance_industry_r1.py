from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['KIE','IAK','XLF','SPY']
START='2009-01-01'; END='2026-09-12'; EP=.0025
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True); OUT=ART/'p566_insurance_industry_r1.json'
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
    q=r.loc[start:end,T].dropna(); x=stats(q.XLF); sp=stats(q.SPY); out={'months':int(len(q)),'xlf':x,'spy':sp}
    for sym in ['KIE','IAK']:
        s=stats(q[sym]); out[sym.lower()]=s; out[sym.lower()+'_minus_xlf_pp']=100*(s['cagr']-x['cagr']); out[sym.lower()+'_minus_spy_pp']=100*(s['cagr']-sp['cagr'])
    return out
windows={'2010+':frame('2010-01-01'),'2015+':frame('2015-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2010_2014':frame('2010-01-01','2014-12-31'),'2015_2019':frame('2015-01-01','2019-12-31'),'2020_2022':frame('2020-01-01','2022-12-31'),'2023_plus':frame('2023-01-01')}
def count(sym,src):
    k=sym.lower()+'_minus_xlf_pp'; return sum(v['months']>=24 and v[k]>0 for v in src.values())
kw=count('KIE',windows); kb=count('KIE',blocks); iw=count('IAK',windows); ib=count('IAK',blocks)
coverage=all(v['months']>=24 for v in blocks.values())
recent=windows['2022+']['kie_minus_xlf_pp']>0 and windows['2022+']['iak_minus_xlf_pp']>0
passed=coverage and kw>=3 and kb>=3 and iw>=3 and ib>=3 and recent
out={'schema':'research.p566_insurance_industry_r1.v1','workload_id':'P566_INSURANCE_INDUSTRY_R1','parent':'INSURANCE_UNDERWRITING_INDUSTRY_PREMIUM','claim':'Insurance-industry exposure should deliver durable after-cost excess versus broad financials XLF across two independent fund implementations; SPY is opportunity context only.','contract':{'endpoint_cost_bps_each':25,'implementations':['KIE','IAK'],'matched_control':'XLF','windows':['2010+','2015+','2020+','2022+'],'blocks':['2010_2014','2015_2019','2020_2022','2023_plus'],'parameter_search':False},'windows':windows,'blocks':blocks,'counts':{'KIE_positive_windows':kw,'KIE_positive_blocks':kb,'IAK_positive_windows':iw,'IAK_positive_blocks':ib},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both KIE and IAK have positive after-cost CAGR excess versus XLF in >=3/4 fixed windows and >=3/4 chronology blocks, both are positive in 2022+, and every block has >=24 months. No alternate insurance fund/control/date/cost rescue.','decision':('INSURANCE_INDUSTRY_PREMIUM_SUPPORTED' if passed else ('INSURANCE_INDUSTRY_SOURCE_COVERAGE_NOT_READY' if not coverage else 'INSURANCE_INDUSTRY_PREMIUM_NOT_SUPPORTED')),'scientific_consequence':('Support a cross-implementation insurance-industry premium relative to broad financials; next falsifier should separate underwriting economics from interest-rate/bank-composition effects before broader promotion.' if passed else ('Record source coverage insufficiency only.' if not coverage else 'Reject the exact broad insurance-industry durable-premium claim without product/control/date rescue; preserve passing subperiods as regime evidence only.')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'KIE_windows_pp':{k:round(v['kie_minus_xlf_pp'],3) for k,v in windows.items()},'IAK_windows_pp':{k:round(v['iak_minus_xlf_pp'],3) for k,v in windows.items()}},sort_keys=True))
