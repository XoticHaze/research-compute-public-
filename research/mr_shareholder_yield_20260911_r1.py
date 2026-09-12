from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T=['PKW','SYLD','SPY','RSP']; START='2013-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_shareholder_yield_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
px=px[T].dropna(how='all')

windows={'2014+':('2014-01-01',None),'2016+':('2016-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2014_2016':('2014-01-01','2016-12-31'),'2017_2019':('2017-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_plus':('2023-01-01',None)}

def stats(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252: return {'days':int(len(s))}
    years=(s.index[-1]-s.index[0]).days/365.2425
    gross=float(s.iloc[-1]/s.iloc[0])
    net=gross*(1-EP)*(1-EP)
    cagr=net**(1/years)-1 if years>0 else np.nan
    wealth=(s/s.iloc[0])*(1-EP)
    dd=float((wealth/wealth.cummax()-1).min())
    return {'days':int(len(s)),'years':float(years),'cagr':float(cagr),'max_drawdown':dd}

def pack(periods):
    out={}
    for k,(a,b) in periods.items():
        row={s:stats(s,a,b) for s in T}
        for s in ['PKW','SYLD']:
            if 'cagr' in row[s] and 'cagr' in row['SPY']:
                row[s]['spy_excess_pp']=float(100*(row[s]['cagr']-row['SPY']['cagr']))
            if 'cagr' in row[s] and 'cagr' in row['RSP']:
                row[s]['rsp_excess_pp']=float(100*(row[s]['cagr']-row['RSP']['cagr']))
        out[k]=row
    return out

W=pack(windows); B=pack(blocks)
posw={s:sum(W[k][s].get('spy_excess_pp',-999)>0 for k in W) for s in ['PKW','SYLD']}
posb={s:sum(B[k][s].get('spy_excess_pp',-999)>0 for k in B) for s in ['PKW','SYLD']}
coverage=all(B[k][s].get('days',0)>=504 for k in B for s in ['PKW','SYLD','SPY'])
passed=coverage and all(posw[s]>=3 and posb[s]>=3 and W['2022+'][s].get('spy_excess_pp',-999)>0 for s in ['PKW','SYLD'])
out={'schema':'research.mr_shareholder_yield_20260911_r1.v1','workload_id':'MR_SHAREHOLDER_YIELD_20260911_R1','parent':'SHAREHOLDER_YIELD_BUYBACK_SELECTION','claim':'If shareholder-yield/buyback selection is a durable equity alpha source rather than implementation-specific exposure, both PKW and SYLD should beat SPY after equal endpoint friction across fixed long windows and disjoint chronology.','contract':{'candidates':['PKW','SYLD'],'matched_control':'SPY','breadth_context':'RSP','endpoint_cost_bps_each_side_each_series':25,'parameter_search':False,'windows':windows,'blocks':blocks},'windows':W,'blocks':B,'positive_spy_excess_windows':posw,'positive_spy_excess_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both candidates beat SPY in >=3/4 windows and >=3/4 blocks and both are positive from 2022+. No product/control/date/cost rescue.','decision':('SHAREHOLDER_YIELD_ALPHA_SUPPORTED' if passed else ('SHAREHOLDER_YIELD_COVERAGE_NOT_READY' if not coverage else 'SHAREHOLDER_YIELD_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'PKW_SPY_pp':{k:round(W[k]['PKW'].get('spy_excess_pp',-999),3) for k in W},'SYLD_SPY_pp':{k:round(W[k]['SYLD'].get('spy_excess_pp',-999),3) for k in W},'counts':{'PKW_positive_windows':posw['PKW'],'PKW_positive_blocks':posb['PKW'],'SYLD_positive_windows':posw['SYLD'],'SYLD_positive_blocks':posb['SYLD']}},sort_keys=True))
