from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['INDA','EPI','VWO','SPY']; START='2012-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_india_selection_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
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
        for s in ['INDA','EPI']:
            out[s+'_minus_VWO_pp']=100*(out[s]['cagr']-out['VWO']['cagr'])
            out[s+'_minus_SPY_pp']=100*(out[s]['cagr']-out['SPY']['cagr'])
    return out
windows={'2013+':frame('2013-01-01'),'2016+':frame('2016-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2013_2016':frame('2013-01-01','2016-12-31'),'2017_2019':frame('2017-01-01','2019-12-31'),'2020_2022':frame('2020-01-01','2022-12-31'),'2023_plus':frame('2023-01-01')}
def count(sym,src):return sum(v.get(sym+'_minus_VWO_pp',-999)>0 for v in src.values())
iw,ib=count('INDA',windows),count('INDA',blocks); ew,eb=count('EPI',windows),count('EPI',blocks)
coverage=all(v[s].get('days',0)>=252 for v in blocks.values() for s in T)
recent=windows['2022+'].get('INDA_minus_VWO_pp',-999)>0 and windows['2022+'].get('EPI_minus_VWO_pp',-999)>0
passed=coverage and iw>=3 and ib>=3 and ew>=3 and eb>=3 and recent
out={'schema':'research.mr_india_selection_20260911_r1.v1','workload_id':'MR_INDIA_SELECTION_20260911_R1','parent':'INDIA_EQUITY_COUNTRY_SELECTION','claim':'If India country selection creates durable excess return versus broad emerging markets rather than a single-index artifact, both INDA and earnings-weighted EPI should beat VWO after fixed endpoint costs across long windows and disjoint chronology; SPY is opportunity-cost context.','contract':{'implementations':['INDA','EPI'],'matched_control':'VWO','opportunity_control':'SPY','endpoint_cost_bps_each':25,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},'windows':windows,'blocks':blocks,'counts':{'INDA_positive_windows':iw,'INDA_positive_blocks':ib,'EPI_positive_windows':ew,'EPI_positive_blocks':eb},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations beat VWO in >=3/4 fixed windows and >=3/4 blocks, both beat VWO from 2022+, and every block has >=252 observations. No country-fund/control/date/cost rescue.','decision':('INDIA_COUNTRY_SELECTION_SUPPORTED' if passed else ('INDIA_SELECTION_SOURCE_COVERAGE_NOT_READY' if not coverage else 'INDIA_COUNTRY_SELECTION_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'INDA_VWO_pp':{k:round(v.get('INDA_minus_VWO_pp',-999),3) for k,v in windows.items()},'EPI_VWO_pp':{k:round(v.get('EPI_minus_VWO_pp',-999),3) for k,v in windows.items()},'INDA_SPY_pp':{k:round(v.get('INDA_minus_SPY_pp',-999),3) for k,v in windows.items()}},sort_keys=True))
