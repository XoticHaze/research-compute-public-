from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['XAR','ITA','XLI','SPY']; START='2011-01-01'; END='2026-09-01'; EP=.0025
OUT=Path('research/artifacts/p437_aero_defense_industry_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None).dropna()

def cagr(x):
    a=np.asarray(x,dtype=float).copy()
    if len(a)<2:return float('nan')
    a[0]-=EP; a[-1]-=EP
    return float(np.prod(1+a)**(12/len(a))-1)

def window(start,end=None):
    q=r.loc[start:end] if end else r.loc[start:]
    o={}
    for f in ('XAR','ITA'):
        fc=cagr(q[f]); xl=cagr(q.XLI); sp=cagr(q.SPY)
        o[f]={'cagr':fc,'xli_excess':fc-xl,'spy_excess':fc-sp,'months':int(len(q))}
    o['implementation_mean_xli_excess']=float(np.mean([o['XAR']['xli_excess'],o['ITA']['xli_excess']]))
    return o
wins={'2012+':window('2012-01-31'),'2016+':window('2016-01-31'),'2020+':window('2020-01-31')}
blocks={'2012_2015':window('2012-01-31','2015-12-31'),'2016_2019':window('2016-01-31','2019-12-31'),'2020_2022':window('2020-01-31','2022-12-31'),'2023_plus':window('2023-01-31')}
all_windows=all(w[f]['xli_excess']>0 for w in wins.values() for f in ('XAR','ITA'))
pos_blocks=sum(b['implementation_mean_xli_excess']>0 for b in blocks.values())
passed=all_windows and pos_blocks>=3
out={'schema':'research.p437_aero_defense_industry_r1.v1','workload_id':'P437_AERO_DEFENSE_INDUSTRY_R1','parent':'P07_INDUSTRY_OPPORTUNITY_ENGINE_SUPPORT','claim':'Aerospace & Defense can qualify as a genuinely third independent industry pool only if two differently weighted implementations (XAR equal-weight and ITA cap-weight) both show after-cost excess over the industrial-sector baseline XLI in every fixed long window and their mean sector-relative excess is positive in at least 3/4 chronology blocks.','data_contract':{'completed_month_end':'2026-08-31','endpoint_cost_bps_each':25,'matched_sector_control':'XLI','opportunity_control':'SPY','parameter_search':False},'windows':wins,'blocks':blocks,'positive_mean_blocks':pos_blocks,'decision_rule':'SUPPORTED only if both XAR and ITA beat XLI after costs in 2012+, 2016+, 2020+ and mean XLI-relative excess is positive in >=3/4 chronology blocks. No product/date/cost/window rescue.','decision':'AEROSPACE_DEFENSE_THIRD_INDUSTRY_EVIDENCE_SUPPORTED' if passed else 'AEROSPACE_DEFENSE_THIRD_INDUSTRY_EVIDENCE_NOT_SUPPORTED','scientific_consequence':('Create scientific evidence for a third independent industry pool; Coordinator alone decides whether this satisfies P06 router resume/admission.' if passed else 'Do not admit Aerospace & Defense as the third industry engine from this formulation; rotate without nearby wrapper rescue.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_mean_blocks':pos_blocks,'windows':{k:{f:round(100*v[f]['xli_excess'],3) for f in ('XAR','ITA')} for k,v in wins.items()},'blocks':{k:round(100*v['implementation_mean_xli_excess'],3) for k,v in blocks.items()}},sort_keys=True))
