from __future__ import annotations
import json
from pathlib import Path
import yfinance as yf, pandas as pd
SYMS=['PUTW','SPY','BIL']; START='2015-01-01'; END='2026-09-10'
out={'schema':'research.p325a_putw_source_adjudication_r1','parent':'P325A','claim':'Diagnose the exact source/representation failure from P325 without changing product, beta window, benchmark, or model thesis. Fetch each predeclared symbol independently, report usable adjusted-price row counts/date ranges, monthly intersections, and whether the causal 36m rolling-beta construction can form observations.','symbols':{},'intersections':{}}
series={}
for s in SYMS:
    try:
        d=yf.download(s,start=START,end=END,auto_adjust=True,progress=False,threads=False)
        c=d['Close']
        if isinstance(c,pd.DataFrame): c=c.iloc[:,0]
        c=c.dropna()
        series[s]=c
        out['symbols'][s]={'rows':int(len(c)),'first':str(c.index.min().date()) if len(c) else None,'last':str(c.index.max().date()) if len(c) else None}
    except Exception as e:
        series[s]=pd.Series(dtype=float)
        out['symbols'][s]={'rows':0,'first':None,'last':None,'error':repr(e)}
for pair in [('PUTW','SPY'),('PUTW','BIL'),('SPY','BIL')]:
    z=pd.concat([series[pair[0]],series[pair[1]]],axis=1).dropna()
    out['intersections']['_'.join(pair)]={'daily_rows':int(len(z)),'first':str(z.index.min().date()) if len(z) else None,'last':str(z.index.max().date()) if len(z) else None}
monthly=pd.concat(series,axis=1).dropna().resample('ME').last().pct_change().dropna() if all(len(series[s]) for s in SYMS) else pd.DataFrame()
if len(monthly):
    ex_put=monthly.PUTW-monthly.BIL; ex_spy=monthly.SPY-monthly.BIL
    beta=(ex_put.rolling(36,min_periods=24).cov(ex_spy)/ex_spy.rolling(36,min_periods=24).var()).shift(1)
    matched=beta*monthly.SPY+(1-beta)*monthly.BIL
    z=pd.concat([monthly.PUTW,matched,beta],axis=1).dropna()
    out['monthly_joint_rows']=int(len(monthly)); out['causal_matched_rows']=int(len(z)); out['causal_first']=str(z.index.min().date()) if len(z) else None
else:
    out['monthly_joint_rows']=0; out['causal_matched_rows']=0; out['causal_first']=None
if out['symbols']['PUTW']['rows']==0: decision='P325A_PUTW_SOURCE_UNAVAILABLE'
elif out['monthly_joint_rows']==0: decision='P325A_JOINT_SOURCE_ALIGNMENT_FAILURE'
elif out['causal_matched_rows']==0: decision='P325A_BENCHMARK_CONSTRUCTION_FAILURE'
else: decision='P325A_SOURCE_AND_BENCHMARK_FORMABLE'
out['decision']=decision
out['boundaries']={'scientific_data_authority':True,'model_inference':False,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p325a_putw_source_adjudication_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))