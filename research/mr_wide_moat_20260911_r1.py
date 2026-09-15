from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T = ['MOAT','SPY','QQQ']
START='2012-01-01'; END='2026-09-12'; EP=0.0025
OUT=Path('research/artifacts/mr_wide_moat_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
px=px[T].dropna(how='all')

def stats(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252: return {'days':int(len(s))}
    years=(s.index[-1]-s.index[0]).days/365.2425
    gross=(float(s.iloc[-1])/float(s.iloc[0]))*((1-EP)**2)
    cagr=gross**(1/years)-1
    r=s.pct_change().dropna()
    wealth=(1+r).cumprod(); dd=wealth/wealth.cummax()-1
    sharpe=(r.mean()/r.std(ddof=1))*math.sqrt(252) if r.std(ddof=1)>0 else float('nan')
    return {'days':int(len(s)),'cagr':float(cagr),'maxdd':float(dd.min()),'sharpe':float(sharpe)}

def frame(start,end=None):
    a=stats('MOAT',start,end); b=stats('SPY',start,end); q=stats('QQQ',start,end)
    out={'MOAT':a,'SPY':b,'QQQ':q}
    if all(x.get('days',0)>=252 for x in [a,b,q]):
        out['moat_minus_spy_cagr_pp']=100*(a['cagr']-b['cagr'])
        out['moat_minus_qqq_cagr_pp']=100*(a['cagr']-q['cagr'])
    return out

windows={'2013+':frame('2013-01-01'),'2016+':frame('2016-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2013_2016':frame('2013-01-01','2016-12-31'),'2017_2019':frame('2017-01-01','2019-12-31'),'2020_2022':frame('2020-01-01','2022-12-31'),'2023_plus':frame('2023-01-01')}
posw=sum(v.get('moat_minus_spy_cagr_pp',-999)>0 for v in windows.values())
posb=sum(v.get('moat_minus_spy_cagr_pp',-999)>0 for v in blocks.values())
coverage=all(v['MOAT'].get('days',0)>=252 and v['SPY'].get('days',0)>=252 for v in blocks.values())
passed=coverage and posw>=3 and posb>=3 and windows['2022+'].get('moat_minus_spy_cagr_pp',-999)>0
out={'schema':'research.mr_wide_moat_20260911_r1.v1','workload_id':'MR_WIDE_MOAT_20260911_R1','parent':'WIDE_MOAT_EQUITY_SELECTION','claim':'If wide-moat plus valuation-aware selection creates durable equity alpha, fixed MOAT should beat SPY after endpoint costs across long windows and disjoint chronology; QQQ is opportunity-cost context only.','contract':{'candidate':'MOAT','matched_control':'SPY','opportunity_control':'QQQ','endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'positive_windows_vs_spy':posw,'positive_blocks_vs_spy':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if MOAT-SPY after-cost CAGR excess is positive in >=3/4 fixed windows and >=3/4 disjoint blocks, positive in 2022+, and every block has >=252 observations. No alternate moat fund/date/cost rescue.','decision':('WIDE_MOAT_SELECTION_SUPPORTED' if passed else ('WIDE_MOAT_SOURCE_COVERAGE_NOT_READY' if not coverage else 'WIDE_MOAT_SELECTION_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_windows':posw,'positive_blocks':posb,'windows_spy_pp':{k:round(v.get('moat_minus_spy_cagr_pp',-999),3) for k,v in windows.items()},'windows_qqq_pp':{k:round(v.get('moat_minus_qqq_cagr_pp',-999),3) for k,v in windows.items()}},sort_keys=True))
