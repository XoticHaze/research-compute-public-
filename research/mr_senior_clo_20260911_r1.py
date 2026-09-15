from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['JAAA','FLRN','SHV','HYG']; START='2020-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_senior_clo_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw

def stats(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252:return {'days':int(len(s)),'first_date':(str(s.index[0].date()) if len(s) else None),'last_date':(str(s.index[-1].date()) if len(s) else None)}
    years=(s.index[-1]-s.index[0]).days/365.2425
    gross=(float(s.iloc[-1])/float(s.iloc[0]))*((1-EP)**2)
    cagr=gross**(1/years)-1
    r=s.pct_change().dropna(); w=(1+r).cumprod(); dd=w/w.cummax()-1
    sh=(r.mean()/r.std(ddof=1))*math.sqrt(252) if r.std(ddof=1)>0 else float('nan')
    return {'days':int(len(s)),'first_date':str(s.index[0].date()),'last_date':str(s.index[-1].date()),'cagr':float(cagr),'maxdd':float(dd.min()),'sharpe':float(sh)}

def frame(start,end=None):
    out={s:stats(s,start,end) for s in T}
    if all(out[s].get('days',0)>=252 for s in T):
        out['JAAA_minus_FLRN_pp']=100*(out['JAAA']['cagr']-out['FLRN']['cagr'])
        out['JAAA_minus_SHV_pp']=100*(out['JAAA']['cagr']-out['SHV']['cagr'])
        out['JAAA_minus_HYG_pp']=100*(out['JAAA']['cagr']-out['HYG']['cagr'])
    return out
windows={'2021+':frame('2021-01-01'),'2022+':frame('2022-01-01'),'2023+':frame('2023-01-01')}
blocks={'2021_2022':frame('2021-01-01','2022-12-31'),'2023_2024':frame('2023-01-01','2024-12-31'),'2025_plus':frame('2025-01-01')}
coverage=all(v['JAAA'].get('days',0)>=378 and v['FLRN'].get('days',0)>=378 and v['SHV'].get('days',0)>=378 for v in blocks.values())
pos_fw=sum(v.get('JAAA_minus_FLRN_pp',-999)>0 for v in windows.values()); pos_fb=sum(v.get('JAAA_minus_FLRN_pp',-999)>0 for v in blocks.values())
pos_sw=sum(v.get('JAAA_minus_SHV_pp',-999)>0 for v in windows.values()); pos_sb=sum(v.get('JAAA_minus_SHV_pp',-999)>0 for v in blocks.values())
recent=windows['2023+'].get('JAAA_minus_FLRN_pp',-999)>0 and windows['2023+'].get('JAAA_minus_SHV_pp',-999)>0
passed=coverage and pos_fw>=2 and pos_fb>=2 and pos_sw>=2 and pos_sb>=2 and recent
out={'schema':'research.mr_senior_clo_20260911_r1.v1','workload_id':'MR_SENIOR_CLO_20260911_R1','parent':'SENIOR_CLO_CARRY_ALPHA','claim':'If AAA CLO structure adds durable after-cost return beyond conventional floating-rate IG credit and ultra-short Treasuries, JAAA should beat both FLRN and SHV across fixed post-inception windows and disjoint chronology; HYG is credit-risk opportunity context.','contract':{'candidate':'JAAA','matched_controls':['FLRN','SHV'],'risk_context':'HYG','endpoint_cost_bps_each':25,'minimum_block_days':378,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'counts':{'positive_windows_vs_FLRN':pos_fw,'positive_blocks_vs_FLRN':pos_fb,'positive_windows_vs_SHV':pos_sw,'positive_blocks_vs_SHV':pos_sb},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if every block has >=378 observations for JAAA/FLRN/SHV, JAAA beats each matched control in >=2/3 windows and >=2/3 blocks, and beats both from 2023+. No date/control/product rescue.','decision':('SENIOR_CLO_CARRY_ALPHA_SUPPORTED' if passed else ('SENIOR_CLO_SOURCE_COVERAGE_NOT_READY' if not coverage else 'SENIOR_CLO_CARRY_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'coverage':coverage,'counts':out['counts'],'windows_flrn_pp':{k:round(v.get('JAAA_minus_FLRN_pp',-999),3) for k,v in windows.items()},'windows_shv_pp':{k:round(v.get('JAAA_minus_SHV_pp',-999),3) for k,v in windows.items()}},sort_keys=True))
