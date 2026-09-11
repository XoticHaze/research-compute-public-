from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import yfinance as yf

T=['ANGL','FALN','HYG','SHY']; START='2016-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_fallen_angels_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
px=px[T]
windows={'2017+':('2017-01-01',None),'2019+':('2019-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2017_2019':('2017-01-01','2019-12-31'),'2020_2021':('2020-01-01','2021-12-31'),'2022_2023':('2022-01-01','2023-12-31'),'2024_plus':('2024-01-01',None)}

def stats(sym,start,end=None):
    s=px[sym].loc[start:end].dropna()
    if len(s)<252:return {'days':int(len(s))}
    years=(s.index[-1]-s.index[0]).days/365.2425
    net=float(s.iloc[-1]/s.iloc[0])*(1-EP)*(1-EP)
    cagr=net**(1/years)-1
    wealth=(s/s.iloc[0])*(1-EP)
    dd=float((wealth/wealth.cummax()-1).min())
    return {'days':int(len(s)),'years':float(years),'cagr':float(cagr),'max_drawdown':dd}

def pack(periods):
    out={}
    for k,(a,b) in periods.items():
        row={s:stats(s,a,b) for s in T}
        for s in ['ANGL','FALN']:
            if 'cagr' in row[s] and 'cagr' in row['HYG']:
                row[s]['hyg_excess_pp']=100*(row[s]['cagr']-row['HYG']['cagr'])
            if 'cagr' in row[s] and 'cagr' in row['SHY']:
                row[s]['shy_excess_pp']=100*(row[s]['cagr']-row['SHY']['cagr'])
        out[k]=row
    return out
W=pack(windows); B=pack(blocks)
posw={s:sum(W[k][s].get('hyg_excess_pp',-999)>0 for k in W) for s in ['ANGL','FALN']}
posb={s:sum(B[k][s].get('hyg_excess_pp',-999)>0 for k in B) for s in ['ANGL','FALN']}
coverage=all(B[k][s].get('days',0)>=450 for k in B for s in ['ANGL','FALN','HYG'])
passed=coverage and all(posw[s]>=3 and posb[s]>=3 and W['2022+'][s].get('hyg_excess_pp',-999)>0 for s in ['ANGL','FALN'])
out={'schema':'research.mr_fallen_angels_20260911_r1.v1','workload_id':'MR_FALLEN_ANGELS_20260911_R1','parent':'FALLEN_ANGEL_CREDIT_SELECTION','claim':'If fallen-angel credit selection captures a durable structural premium rather than one-fund construction luck, both ANGL and FALN should beat broad high-yield HYG after equal endpoint friction across common long windows and disjoint chronology.','contract':{'candidates':['ANGL','FALN'],'matched_control':'HYG','cash_duration_context':'SHY','endpoint_cost_bps_each_side_each_series':25,'parameter_search':False,'windows':windows,'blocks':blocks},'windows':W,'blocks':B,'positive_hyg_excess_windows':posw,'positive_hyg_excess_blocks':posb,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both candidates beat HYG in >=3/4 windows and >=3/4 blocks and both are positive from 2022+. No product/control/date/cost rescue.','decision':('FALLEN_ANGEL_PREMIUM_SUPPORTED' if passed else ('FALLEN_ANGEL_COVERAGE_NOT_READY' if not coverage else 'FALLEN_ANGEL_PREMIUM_NOT_SUPPORTED')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'ANGL_HYG_pp':{k:round(W[k]['ANGL'].get('hyg_excess_pp',-999),3) for k in W},'FALN_HYG_pp':{k:round(W[k]['FALN'].get('hyg_excess_pp',-999),3) for k in W},'counts':{'ANGL_positive_windows':posw['ANGL'],'ANGL_positive_blocks':posb['ANGL'],'FALN_positive_windows':posw['FALN'],'FALN_positive_blocks':posb['FALN']}},sort_keys=True))
