from __future__ import annotations
import json
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
T=['XBI','IBB','XLV','SPY']; START='2010-01-01'; END='2026-09-01'; EP=.0025
OUT=Path('research/artifacts/p441_biotech_industry_r1.json');OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False); c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None).dropna()
def cagr(x):
 a=np.asarray(x,float).copy(); a[0]-=EP;a[-1]-=EP;return float(np.prod(1+a)**(12/len(a))-1)
def w(a,b=None):
 q=r.loc[a:b] if b else r.loc[a:];o={}
 for f in ('XBI','IBB'):
  fc=cagr(q[f]);o[f]={'xlv_excess':fc-cagr(q.XLV),'spy_excess':fc-cagr(q.SPY),'cagr':fc,'months':len(q)}
 o['mean_xlv_excess']=float(np.mean([o[x]['xlv_excess'] for x in ('XBI','IBB')]))
 return o
wins={'2011+':w('2011-01-31'),'2016+':w('2016-01-31'),'2020+':w('2020-01-31')};blocks={'2011_2015':w('2011-01-31','2015-12-31'),'2016_2019':w('2016-01-31','2019-12-31'),'2020_2022':w('2020-01-31','2022-12-31'),'2023_plus':w('2023-01-31')}
passx=all(v[f]['xlv_excess']>0 for v in wins.values() for f in ('XBI','IBB')) and sum(v['mean_xlv_excess']>0 for v in blocks.values())>=3
out={'schema':'research.p441_biotech_industry_r1.v1','workload_id':'P441_BIOTECH_INDUSTRY_R1','parent':'P07_INDUSTRY_OPPORTUNITY_ENGINE_SUPPORT','claim':'Biotechnology qualifies as a third independent industry only if both XBI and IBB show after-cost excess over matched healthcare control XLV in every fixed long window and their mean XLV-relative excess is positive in >=3/4 chronology blocks.','windows':wins,'blocks':blocks,'decision_rule':'Both implementations > XLV in 2011+/2016+/2020+ and mean sector excess positive >=3/4 blocks; no ETF/date/cost/threshold rescue.','decision':'BIOTECH_THIRD_INDUSTRY_EVIDENCE_SUPPORTED' if passx else 'BIOTECH_THIRD_INDUSTRY_EVIDENCE_NOT_SUPPORTED','boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False));print(json.dumps({'decision':out['decision'],'windows':{k:{f:round(100*v[f]['xlv_excess'],3) for f in ('XBI','IBB')} for k,v in wins.items()},'blocks':{k:round(100*v['mean_xlv_excess'],3) for k,v in blocks.items()}},sort_keys=True))