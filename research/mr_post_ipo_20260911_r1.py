from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['FPX','IPO','SPY','QQQ']; START='2013-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_post_ipo_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
px=px[T]
windows={'2014+':('2014-01-01',None),'2016+':('2016-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2014_2016':('2014-01-01','2016-12-31'),'2017_2019':('2017-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_plus':('2023-01-01',None)}

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
        for s in ['FPX','IPO']:
            if 'cagr' in row[s] and 'cagr' in row['SPY']: row[s]['spy_excess_pp']=100*(row[s]['cagr']-row['SPY']['cagr'])
            if 'cagr' in row[s] and 'cagr' in row['QQQ']: row[s]['qqq_excess_pp']=100*(row[s]['cagr']-row['QQQ']['cagr'])
        out[k]=row
    return out
W=pack(windows); B=pack(blocks)
posw={s:sum(W[k][s].get('spy_excess_pp',-999)>0 for k in W) for s in ['FPX','IPO']}
posb={s:sum(B[k][s].get('spy_excess_pp',-999)>0 for k in B) for s in ['FPX','IPO']}
coverage=all(B[k][s].get('days',0)>=500 for k in B for s in ['FPX','IPO','SPY'])
passed=coverage and all(posw[s]>=3 and posb[s]>=3 and W['2022+'][s].get('spy_excess_pp',-999)>0 for s in ['FPX','IPO'])
out={'schema':'research.mr_post_ipo_20260911_r1.v1','workload_id':'MR_POST_IPO_20260911_R1','parent':'POST_IPO_EQUITY_SELECTION','claim':'If post-IPO seasoning/selection creates durable equity alpha rather than cycle-specific new-issue exposure, both FPX and IPO should beat SPY after equal endpoint friction across fixed long windows and disjoint chronology, with QQQ retained as growth opportunity context.','contract':{'candidates':['FPX','IPO'],'matched_control':'SPY','growth_context':'QQQ','endpoint_cost_bps_each_side_each_series':25,'parameter_search':False,'windows':windows,'blocks':blocks},'windows':W,'blocks':B,'positive_spy_excess_windows':posw,'positive_spy_excess_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both candidates beat SPY in >=3/4 windows and >=3/4 blocks and both are positive from 2022+. QQQ is opportunity context, not a rescue control. No product/control/date/cost rescue.','decision':('POST_IPO_ALPHA_SUPPORTED' if passed else ('POST_IPO_COVERAGE_NOT_READY' if not coverage else 'POST_IPO_ALPHA_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'FPX_SPY_pp':{k:round(W[k]['FPX'].get('spy_excess_pp',-999),3) for k in W},'IPO_SPY_pp':{k:round(W[k]['IPO'].get('spy_excess_pp',-999),3) for k in W},'counts':{'FPX_positive_windows':posw['FPX'],'FPX_positive_blocks':posb['FPX'],'IPO_positive_windows':posw['IPO'],'IPO_positive_blocks':posb['IPO']},'QQQ_2022plus_pp':{'FPX':round(W['2022+']['FPX'].get('qqq_excess_pp',-999),3),'IPO':round(W['2022+']['IPO'].get('qqq_excess_pp',-999),3)}},sort_keys=True))
