from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['COWZ','CALF','SPY','IWM']; START='2017-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_free_cash_flow_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
px=px[T]
windows={'2018+':('2018-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None),'2024+':('2024-01-01',None)}
blocks={'2018_2019':('2018-01-01','2019-12-31'),'2020_2021':('2020-01-01','2021-12-31'),'2022_2023':('2022-01-01','2023-12-31'),'2024_plus':('2024-01-01',None)}
MAP={'COWZ':'SPY','CALF':'IWM'}

def stats(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252:return {'days':int(len(s))}
    years=(s.index[-1]-s.index[0]).days/365.2425
    net=float(s.iloc[-1]/s.iloc[0])*(1-EP)*(1-EP); cagr=net**(1/years)-1
    wealth=(s/s.iloc[0])*(1-EP); dd=float((wealth/wealth.cummax()-1).min())
    return {'days':int(len(s)),'years':float(years),'cagr':float(cagr),'max_drawdown':dd}

def pack(periods):
    out={}
    for k,(a,b) in periods.items():
        row={s:stats(s,a,b) for s in T}
        for s,c in MAP.items():
            if 'cagr' in row[s] and 'cagr' in row[c]: row[s]['matched_excess_pp']=100*(row[s]['cagr']-row[c]['cagr'])
        out[k]=row
    return out
W=pack(windows); B=pack(blocks)
posw={s:sum(W[k][s].get('matched_excess_pp',-999)>0 for k in W) for s in MAP}
posb={s:sum(B[k][s].get('matched_excess_pp',-999)>0 for k in B) for s in MAP}
coverage=all(B[k][s].get('days',0)>=400 for k in B for s in T)
passed=coverage and all(posw[s]>=3 and posb[s]>=3 and W['2022+'][s].get('matched_excess_pp',-999)>0 for s in MAP)
out={'schema':'research.mr_free_cash_flow_20260911_r1.v1','workload_id':'MR_FREE_CASH_FLOW_20260911_R1','parent':'FREE_CASH_FLOW_EQUITY_SELECTION','claim':'If free-cash-flow selection is a transportable equity alpha mechanism rather than one-universe implementation luck, COWZ should beat SPY and CALF should beat IWM after equal endpoint friction across fixed long windows and disjoint chronology.','contract':{'matched_pairs':MAP,'endpoint_cost_bps_each_side_each_series':25,'parameter_search':False,'windows':windows,'blocks':blocks},'windows':W,'blocks':B,'positive_matched_excess_windows':posw,'positive_matched_excess_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations beat their matched universes in >=3/4 windows and >=3/4 blocks and both are positive from 2022+. No product/control/date/cost rescue.','decision':('FREE_CASH_FLOW_ALPHA_SUPPORTED' if passed else ('FREE_CASH_FLOW_COVERAGE_NOT_READY' if not coverage else 'FREE_CASH_FLOW_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'COWZ_SPY_pp':{k:round(W[k]['COWZ'].get('matched_excess_pp',-999),3) for k in W},'CALF_IWM_pp':{k:round(W[k]['CALF'].get('matched_excess_pp',-999),3) for k in W},'counts':{'COWZ_positive_windows':posw['COWZ'],'COWZ_positive_blocks':posb['COWZ'],'CALF_positive_windows':posw['CALF'],'CALF_positive_blocks':posb['CALF']}},sort_keys=True))
