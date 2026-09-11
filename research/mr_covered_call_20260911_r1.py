from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T=['QYLD','XYLD','QQQ','SPY','BIL']; START='2013-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_covered_call_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
px=px[T]
windows={'2014+':('2014-01-01',None),'2016+':('2016-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2014_2016':('2014-01-01','2016-12-31'),'2017_2019':('2017-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_plus':('2023-01-01',None)}
MAP={'QYLD':'QQQ','XYLD':'SPY'}

def stats(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252:return {'days':int(len(s))}
    daily=s.pct_change().dropna(); years=(s.index[-1]-s.index[0]).days/365.2425
    net=float(s.iloc[-1]/s.iloc[0])*(1-EP)*(1-EP); cagr=net**(1/years)-1
    wealth=(s/s.iloc[0])*(1-EP); dd=float((wealth/wealth.cummax()-1).min())
    annret=float(daily.mean()*252); annvol=float(daily.std(ddof=1)*math.sqrt(252)); sharpe=annret/annvol if annvol>0 else None
    return {'days':int(len(s)),'years':float(years),'cagr':float(cagr),'max_drawdown':dd,'ann_vol':annvol,'simple_sharpe':sharpe}

def pack(periods):
    out={}
    for k,(a,b) in periods.items():
        row={s:stats(s,a,b) for s in T}
        for s,c in MAP.items():
            if 'cagr' in row[s] and 'cagr' in row[c]:
                row[s]['matched_excess_pp']=100*(row[s]['cagr']-row[c]['cagr'])
                row[s]['matched_drawdown_delta_pp']=100*(row[s]['max_drawdown']-row[c]['max_drawdown'])
                if row[s].get('simple_sharpe') is not None and row[c].get('simple_sharpe') is not None:
                    row[s]['matched_sharpe_delta']=row[s]['simple_sharpe']-row[c]['simple_sharpe']
        out[k]=row
    return out
W=pack(windows); B=pack(blocks)
posw={s:sum(W[k][s].get('matched_excess_pp',-999)>0 for k in W) for s in MAP}
posb={s:sum(B[k][s].get('matched_excess_pp',-999)>0 for k in B) for s in MAP}
coverage=all(B[k][s].get('days',0)>=500 for k in B for s in ['QYLD','XYLD','QQQ','SPY'])
passed=coverage and all(posw[s]>=3 and posb[s]>=3 and W['2022+'][s].get('matched_excess_pp',-999)>0 for s in MAP)
out={'schema':'research.mr_covered_call_20260911_r1.v1','workload_id':'MR_COVERED_CALL_20260911_R1','parent':'SYSTEMATIC_COVERED_CALL_OVERWRITE','claim':'If systematic covered-call overwrite creates durable alpha rather than merely reshaping equity risk, QYLD and XYLD should beat their own matched underlyings QQQ and SPY after equal endpoint friction across fixed long windows and disjoint chronology.','contract':{'matched_pairs':MAP,'endpoint_cost_bps_each_side_each_series':25,'parameter_search':False,'windows':windows,'blocks':blocks},'windows':W,'blocks':B,'positive_matched_excess_windows':posw,'positive_matched_excess_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both covered-call implementations beat their matched underlying in >=3/4 windows and >=3/4 blocks and both are positive from 2022+. Risk-shaping evidence may be preserved separately; no product/control/date/cost rescue.','decision':('COVERED_CALL_ALPHA_SUPPORTED' if passed else ('COVERED_CALL_COVERAGE_NOT_READY' if not coverage else 'COVERED_CALL_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'QYLD_QQQ_pp':{k:round(W[k]['QYLD'].get('matched_excess_pp',-999),3) for k in W},'XYLD_SPY_pp':{k:round(W[k]['XYLD'].get('matched_excess_pp',-999),3) for k in W},'counts':{'QYLD_positive_windows':posw['QYLD'],'QYLD_positive_blocks':posb['QYLD'],'XYLD_positive_windows':posw['XYLD'],'XYLD_positive_blocks':posb['XYLD']},'risk_2022plus':{'QYLD_sharpe_delta':round(W['2022+']['QYLD'].get('matched_sharpe_delta',-999),3),'QYLD_dd_delta_pp':round(W['2022+']['QYLD'].get('matched_drawdown_delta_pp',-999),3),'XYLD_sharpe_delta':round(W['2022+']['XYLD'].get('matched_sharpe_delta',-999),3),'XYLD_dd_delta_pp':round(W['2022+']['XYLD'].get('matched_drawdown_delta_pp',-999),3)}},sort_keys=True))
