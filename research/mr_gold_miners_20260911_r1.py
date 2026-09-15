from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['GDX','RING','GLD','SPY']; START='2012-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_gold_miners_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
px=px[T]
windows={'2013+':('2013-01-01',None),'2016+':('2016-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2013_2015':('2013-01-01','2015-12-31'),'2016_2018':('2016-01-01','2018-12-31'),'2019_2021':('2019-01-01','2021-12-31'),'2022_2024':('2022-01-01','2024-12-31'),'2025_plus':('2025-01-01',None)}

def stats(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252:return {'days':int(len(s))}
    years=(s.index[-1]-s.index[0]).days/365.2425
    net=float(s.iloc[-1]/s.iloc[0])*(1-EP)*(1-EP)
    cagr=net**(1/years)-1
    wealth=(s/s.iloc[0])*(1-EP); dd=float((wealth/wealth.cummax()-1).min())
    return {'days':int(len(s)),'years':float(years),'cagr':float(cagr),'max_drawdown':dd}

def pack(periods):
    out={}
    for k,(a,b) in periods.items():
        row={s:stats(s,a,b) for s in T}
        for s in ['GDX','RING']:
            if 'cagr' in row[s] and 'cagr' in row['GLD']: row[s]['gld_excess_pp']=100*(row[s]['cagr']-row['GLD']['cagr'])
            if 'cagr' in row[s] and 'cagr' in row['SPY']: row[s]['spy_excess_pp']=100*(row[s]['cagr']-row['SPY']['cagr'])
        out[k]=row
    return out
W=pack(windows); B=pack(blocks)
posw={s:sum(W[k][s].get('gld_excess_pp',-999)>0 for k in W) for s in ['GDX','RING']}
posb={s:sum(B[k][s].get('gld_excess_pp',-999)>0 for k in B) for s in ['GDX','RING']}
coverage=all(B[k][s].get('days',0)>=400 for k in B for s in ['GDX','RING','GLD'])
passed=coverage and all(posw[s]>=3 and posb[s]>=3 and W['2022+'][s].get('gld_excess_pp',-999)>0 for s in ['GDX','RING'])
out={'schema':'research.mr_gold_miners_20260911_r1.v1','workload_id':'MR_GOLD_MINERS_20260911_R1','parent':'GOLD_MINER_OPERATING_LEVERAGE_ALPHA','claim':'If gold-miner operating leverage creates durable producer alpha beyond the underlying metal, both GDX and RING should beat GLD after equal endpoint friction across fixed long windows and disjoint chronology.','contract':{'candidates':['GDX','RING'],'matched_control':'GLD','opportunity_context':'SPY','endpoint_cost_bps_each_side_each_series':25,'parameter_search':False,'windows':windows,'blocks':blocks},'windows':W,'blocks':B,'positive_gld_excess_windows':posw,'positive_gld_excess_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both candidates beat GLD in >=3/4 windows and >=3/5 blocks and both are positive from 2022+. No product/control/date/cost rescue.','decision':('GOLD_MINER_ALPHA_SUPPORTED' if passed else ('GOLD_MINER_COVERAGE_NOT_READY' if not coverage else 'GOLD_MINER_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'GDX_GLD_pp':{k:round(W[k]['GDX'].get('gld_excess_pp',-999),3) for k in W},'RING_GLD_pp':{k:round(W[k]['RING'].get('gld_excess_pp',-999),3) for k in W},'counts':{'GDX_positive_windows':posw['GDX'],'GDX_positive_blocks':posb['GDX'],'RING_positive_windows':posw['RING'],'RING_positive_blocks':posb['RING']}},sort_keys=True))
