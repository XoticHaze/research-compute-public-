from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['IBB','XBI','XLV','SPY']; START='2009-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_biotech_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw

def stats(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252:return {'days':int(len(s))}
    years=(s.index[-1]-s.index[0]).days/365.2425
    gross=(float(s.iloc[-1])/float(s.iloc[0]))*((1-EP)**2)
    cagr=gross**(1/years)-1
    r=s.pct_change().dropna(); w=(1+r).cumprod(); dd=w/w.cummax()-1
    sh=(r.mean()/r.std(ddof=1))*math.sqrt(252) if r.std(ddof=1)>0 else float('nan')
    return {'days':int(len(s)),'cagr':float(cagr),'maxdd':float(dd.min()),'sharpe':float(sh)}

def frame(start,end=None):
    out={s:stats(s,start,end) for s in T}
    if all(out[s].get('days',0)>=252 for s in T):
        for s in ['IBB','XBI']:
            out[s+'_minus_XLV_pp']=100*(out[s]['cagr']-out['XLV']['cagr'])
            out[s+'_minus_SPY_pp']=100*(out[s]['cagr']-out['SPY']['cagr'])
    return out
windows={'2010+':frame('2010-01-01'),'2015+':frame('2015-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2010_2013':frame('2010-01-01','2013-12-31'),'2014_2017':frame('2014-01-01','2017-12-31'),'2018_2021':frame('2018-01-01','2021-12-31'),'2022_plus':frame('2022-01-01')}
def count(sym,src):return sum(v.get(sym+'_minus_XLV_pp',-999)>0 for v in src.values())
iw,ib=count('IBB',windows),count('IBB',blocks); xw,xb=count('XBI',windows),count('XBI',blocks)
coverage=all(v[s].get('days',0)>=252 for v in blocks.values() for s in T)
recent=windows['2022+'].get('IBB_minus_XLV_pp',-999)>0 and windows['2022+'].get('XBI_minus_XLV_pp',-999)>0
passed=coverage and iw>=3 and ib>=3 and xw>=3 and xb>=3 and recent
out={'schema':'research.mr_biotech_20260911_r1.v1','workload_id':'MR_BIOTECH_20260911_R1','parent':'BIOTECH_INDUSTRY_SELECTION','claim':'If biotech specialization creates durable healthcare-sector excess return, both cap-weighted IBB and equal-weighted XBI should beat broad healthcare XLV after fixed endpoint costs across long windows and disjoint chronology; SPY is broad-market opportunity context.','contract':{'implementations':['IBB','XBI'],'matched_control':'XLV','opportunity_control':'SPY','endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'counts':{'IBB_positive_windows':iw,'IBB_positive_blocks':ib,'XBI_positive_windows':xw,'XBI_positive_blocks':xb},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations beat XLV in >=3/4 windows and >=3/4 blocks, both beat XLV from 2022+, and every block has >=252 observations. No wrapper/control/date/cost rescue.','decision':('BIOTECH_SELECTION_SUPPORTED' if passed else ('BIOTECH_SOURCE_COVERAGE_NOT_READY' if not coverage else 'BIOTECH_SELECTION_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'IBB_XLV_pp':{k:round(v.get('IBB_minus_XLV_pp',-999),3) for k,v in windows.items()},'XBI_XLV_pp':{k:round(v.get('XBI_minus_XLV_pp',-999),3) for k,v in windows.items()},'IBB_SPY_pp':{k:round(v.get('IBB_minus_SPY_pp',-999),3) for k,v in windows.items()}},sort_keys=True))
