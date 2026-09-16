from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['EEMS','VWO','SPY','BIL']
START='2011-01-01'; END='2026-09-12'; EP=.0025
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True); OUT=ART/'p555_eems_em_smallcap_r1.json'
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None).dropna(how='all')

def stats(s:pd.Series):
    x=s.dropna().astype(float)
    if len(x)<12:return {'months':int(len(x))}
    y=x.to_numpy().copy(); y[0]-=EP; y[-1]-=EP
    wealth=np.cumprod(1+y); yrs=len(y)/12
    cagr=float(wealth[-1]**(1/yrs)-1)
    vol=float(np.std(y,ddof=1)*math.sqrt(12)); sharpe=float(np.mean(y)*12/vol) if vol>0 else None
    dd=float(np.min(wealth/np.maximum.accumulate(wealth)-1))
    return {'months':int(len(y)),'cagr':cagr,'vol':vol,'sharpe':sharpe,'max_drawdown':dd}

def ex(start,end=None):
    q=r.loc[start:end,['EEMS','VWO','SPY','BIL']].dropna()
    a=stats(q.EEMS); b=stats(q.VWO); s=stats(q.SPY)
    return {'months':int(len(q)),'eems':a,'vwo':b,'spy':s,'matched_excess_pp':100*(a['cagr']-b['cagr']),'spy_opportunity_pp':100*(a['cagr']-s['cagr'])}
windows={'2012+':ex('2012-01-01'),'2016+':ex('2016-01-01'),'2020+':ex('2020-01-01'),'2022+':ex('2022-01-01')}
blocks={'2012_2015':ex('2012-01-01','2015-12-31'),'2016_2019':ex('2016-01-01','2019-12-31'),'2020_2022':ex('2020-01-01','2022-12-31'),'2023_plus':ex('2023-01-01')}
posw=sum(v['months']>=24 and v['matched_excess_pp']>0 for v in windows.values())
posb=sum(v['months']>=18 and v['matched_excess_pp']>0 for v in blocks.values())
recent=windows['2020+']['matched_excess_pp']
passed=posw>=3 and posb>=3 and recent>0
out={'schema':'research.p555_eems_em_smallcap_r1.v1','workload_id':'P555_EEMS_EM_SMALLCAP_R1','parent':'EMERGING_MARKET_SMALL_CAP_FACTOR','claim':'EEMS should deliver durable after-cost excess versus broad emerging-market VWO across fixed long windows and chronology blocks; SPY is opportunity context only.','contract':{'endpoint_cost_bps_each':25,'windows':['2012+','2016+','2020+','2022+'],'blocks':['2012_2015','2016_2019','2020_2022','2023_plus'],'parameter_search':False},'windows':windows,'blocks':blocks,'positive_windows':int(posw),'positive_blocks':int(posb),'decision_rule':'SUPPORTED only if >=3/4 fixed long windows and >=3/4 chronology blocks have positive EEMS-VWO after-cost CAGR excess and the 2020+ window is positive. No alternate product/date/cost/threshold rescue.','decision':'EM_SMALLCAP_FACTOR_SUPPORTED' if passed else 'EM_SMALLCAP_FACTOR_NOT_SUPPORTED','scientific_consequence':('Treat emerging-market small-cap as a scoped survivor requiring one independent implementation or mechanism falsifier; no portfolio ranking/allocation authority.' if passed else 'Reject the exact EEMS EM-small-cap durable-alpha claim without substituting another fund or moving dates; any positive subperiods remain regime evidence only.'),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_windows':posw,'positive_blocks':posb,'windows_pp':{k:round(v['matched_excess_pp'],3) for k,v in windows.items()},'blocks_pp':{k:round(v['matched_excess_pp'],3) for k,v in blocks.items()}},sort_keys=True))
