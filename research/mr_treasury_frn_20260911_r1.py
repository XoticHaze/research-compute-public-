from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['USFR','TFLO','SHV','BIL']; START='2014-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_treasury_frn_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw

def stats(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252:return {'days':int(len(s))}
    years=(s.index[-1]-s.index[0]).days/365.2425
    gross=(float(s.iloc[-1])/float(s.iloc[0]))*((1-EP)**2 if sym in ['USFR','TFLO'] else 1.0)
    cagr=gross**(1/years)-1
    r=s.pct_change().dropna(); w=(1+r).cumprod(); dd=w/w.cummax()-1
    sh=(r.mean()/r.std(ddof=1))*math.sqrt(252) if r.std(ddof=1)>0 else float('nan')
    return {'days':int(len(s)),'cagr':float(cagr),'maxdd':float(dd.min()),'sharpe':float(sh)}

def frame(start,end=None):
    out={s:stats(s,start,end) for s in T}
    if all(out[s].get('days',0)>=252 for s in T):
        for s in ['USFR','TFLO']:
            out[s+'_minus_SHV_pp']=100*(out[s]['cagr']-out['SHV']['cagr'])
            out[s+'_minus_BIL_pp']=100*(out[s]['cagr']-out['BIL']['cagr'])
    return out
windows={'2015+':frame('2015-01-01'),'2018+':frame('2018-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2015_2017':frame('2015-01-01','2017-12-31'),'2018_2020':frame('2018-01-01','2020-12-31'),'2021_2023':frame('2021-01-01','2023-12-31'),'2024_plus':frame('2024-01-01')}
def count(sym,src):return sum(v.get(sym+'_minus_SHV_pp',-999)>0 for v in src.values())
uw,ub=count('USFR',windows),count('USFR',blocks); tw,tb=count('TFLO',windows),count('TFLO',blocks)
coverage=all(v[s].get('days',0)>=252 for v in blocks.values() for s in T)
recent=windows['2022+'].get('USFR_minus_SHV_pp',-999)>0 and windows['2022+'].get('TFLO_minus_SHV_pp',-999)>0
passed=coverage and uw>=3 and ub>=3 and tw>=3 and tb>=3 and recent
out={'schema':'research.mr_treasury_frn_20260911_r1.v1','workload_id':'MR_TREASURY_FRN_20260911_R1','parent':'TREASURY_FLOATING_RATE_CARRY','claim':'If Treasury floating-rate notes create durable cash-management excess without credit risk, both USFR and TFLO should beat ultra-short Treasury SHV after fixed endpoint friction across long windows and disjoint chronology; BIL is cash context.','contract':{'implementations':['USFR','TFLO'],'matched_control':'SHV','cash_context':'BIL','candidate_endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'counts':{'USFR_positive_windows':uw,'USFR_positive_blocks':ub,'TFLO_positive_windows':tw,'TFLO_positive_blocks':tb},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations beat SHV in >=3/4 windows and >=3/4 blocks, both beat SHV from 2022+, and every block has >=252 observations. No product/control/date/cost rescue.','decision':('TREASURY_FRN_CARRY_SUPPORTED' if passed else ('TREASURY_FRN_SOURCE_COVERAGE_NOT_READY' if not coverage else 'TREASURY_FRN_CARRY_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'USFR_SHV_pp':{k:round(v.get('USFR_minus_SHV_pp',-999),3) for k,v in windows.items()},'TFLO_SHV_pp':{k:round(v.get('TFLO_minus_SHV_pp',-999),3) for k,v in windows.items()}},sort_keys=True))
