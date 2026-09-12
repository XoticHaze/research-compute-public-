from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['KRE','QABA','XLF','SPY']; START='2009-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_regional_banks_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
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
        for s in ['KRE','QABA']:
            out[s+'_minus_XLF_pp']=100*(out[s]['cagr']-out['XLF']['cagr'])
            out[s+'_minus_SPY_pp']=100*(out[s]['cagr']-out['SPY']['cagr'])
    return out
windows={'2010+':frame('2010-01-01'),'2015+':frame('2015-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2010_2013':frame('2010-01-01','2013-12-31'),'2014_2017':frame('2014-01-01','2017-12-31'),'2018_2021':frame('2018-01-01','2021-12-31'),'2022_plus':frame('2022-01-01')}
def count(sym,src):return sum(v.get(sym+'_minus_XLF_pp',-999)>0 for v in src.values())
kw,kb=count('KRE',windows),count('KRE',blocks); qw,qb=count('QABA',windows),count('QABA',blocks)
coverage=all(v[s].get('days',0)>=252 for v in blocks.values() for s in T)
recent=windows['2022+'].get('KRE_minus_XLF_pp',-999)>0 and windows['2022+'].get('QABA_minus_XLF_pp',-999)>0
passed=coverage and kw>=3 and kb>=3 and qw>=3 and qb>=3 and recent
out={'schema':'research.mr_regional_banks_20260911_r1.v1','workload_id':'MR_REGIONAL_BANKS_20260911_R1','parent':'REGIONAL_COMMUNITY_BANK_SPECIALIZATION','claim':'If regional/community-bank specialization creates durable financial-sector excess return, both KRE and QABA should beat broad financials XLF after fixed endpoint costs across long windows and disjoint chronology; SPY is opportunity-cost context.','contract':{'implementations':['KRE','QABA'],'matched_control':'XLF','opportunity_control':'SPY','endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'counts':{'KRE_positive_windows':kw,'KRE_positive_blocks':kb,'QABA_positive_windows':qw,'QABA_positive_blocks':qb},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations beat XLF in >=3/4 fixed windows and >=3/4 blocks, both beat XLF from 2022+, and every block has >=252 observations. No wrapper/control/date/cost rescue.','decision':('REGIONAL_BANK_PREMIUM_SUPPORTED' if passed else ('REGIONAL_BANK_SOURCE_COVERAGE_NOT_READY' if not coverage else 'REGIONAL_BANK_PREMIUM_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'KRE_XLF_pp':{k:round(v.get('KRE_minus_XLF_pp',-999),3) for k,v in windows.items()},'QABA_XLF_pp':{k:round(v.get('QABA_minus_XLF_pp',-999),3) for k,v in windows.items()}},sort_keys=True))
