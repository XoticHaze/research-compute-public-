from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['XSOE','EMXC','VWO','SPY']
START='2017-01-01'; END='2026-09-12'; EP=.0025
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True); OUT=ART/'p559_xsoe_country_control_r1.json'
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None)

def stats(s):
    x=s.dropna().astype(float)
    if len(x)<12:return {'months':int(len(x))}
    y=x.to_numpy().copy(); y[0]-=EP; y[-1]-=EP
    w=np.cumprod(1+y); yrs=len(y)/12
    cagr=float(w[-1]**(1/yrs)-1); vol=float(np.std(y,ddof=1)*math.sqrt(12)); sh=float(np.mean(y)*12/vol) if vol>0 else None
    dd=float(np.min(w/np.maximum.accumulate(w)-1))
    return {'months':int(len(y)),'cagr':cagr,'vol':vol,'sharpe':sh,'max_drawdown':dd}

def frame(start,end=None):
    q=r.loc[start:end,T].dropna()
    x=stats(q.XSOE); e=stats(q.EMXC); v=stats(q.VWO); s=stats(q.SPY)
    return {'months':int(len(q)),'xsoe':x,'emxc':e,'vwo':v,'spy':s,
            'xsoe_minus_emxc_pp':100*(x['cagr']-e['cagr']),
            'xsoe_minus_vwo_pp':100*(x['cagr']-v['cagr']),
            'emxc_minus_vwo_pp':100*(e['cagr']-v['cagr'])}
windows={'2018+':frame('2018-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2018_2020':frame('2018-01-01','2020-12-31'),'2021_2023':frame('2021-01-01','2023-12-31'),'2024_plus':frame('2024-01-01')}
posw=sum(v['months']>=24 and v['xsoe_minus_emxc_pp']>0 for v in windows.values())
posb=sum(v['months']>=18 and v['xsoe_minus_emxc_pp']>0 for v in blocks.values())
coverage=all(v['months']>=18 for v in blocks.values())
full=windows['2018+']
passed=coverage and posw>=2 and posb>=2 and full['xsoe_minus_emxc_pp']>0 and full['xsoe_minus_vwo_pp']>0
out={'schema':'research.p559_xsoe_country_control_r1.v1','workload_id':'P559_XSOE_COUNTRY_CONTROL_R1','parent':'EMERGING_MARKET_GOVERNANCE_SELECTION','claim':'If XSOE governance selection is more than an ex-China/country-composition effect, XSOE should retain positive after-cost excess versus EMXC on fixed common-history windows and chronology while also remaining positive versus VWO.','contract':{'endpoint_cost_bps_each':25,'windows':['2018+','2020+','2022+'],'blocks':['2018_2020','2021_2023','2024_plus'],'parameter_search':False},'windows':windows,'blocks':blocks,'positive_xsoe_minus_emxc_windows':int(posw),'positive_xsoe_minus_emxc_blocks':int(posb),'coverage_ready':coverage,'decision_rule':'GOVERNANCE_ATTRIBUTION_SUPPORTED only if all blocks have >=18 common months, XSOE beats EMXC in >=2/3 fixed windows and >=2/3 chronology blocks, and full 2018+ XSOE excess is positive versus both EMXC and VWO. No alternate country-control product/date/cost rescue.','decision':('EM_GOVERNANCE_ATTRIBUTION_SUPPORTED' if passed else ('EM_GOVERNANCE_COUNTRY_CONTROL_SOURCE_COVERAGE_NOT_READY' if not coverage else 'EM_GOVERNANCE_ATTRIBUTION_NOT_SUPPORTED')),'scientific_consequence':('Strengthen XSOE governance-mechanism attribution beyond simple ex-China composition, while preserving regime weakness and requiring another independent mechanism/source falsifier before broad promotion.' if passed else ('Record data/coverage insufficiency only; preserve P557 raw XSOE-VWO evidence.' if not coverage else 'Treat P557 raw XSOE-VWO support as country-composition-confounded: preserve the observed wrapper excess but do not attribute it specifically to governance selection. No alternate control rescue.')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'positive_windows':posw,'positive_blocks':posb,'windows_xsoe_emxc_pp':{k:round(v['xsoe_minus_emxc_pp'],3) for k,v in windows.items()},'blocks_xsoe_emxc_pp':{k:round(v['xsoe_minus_emxc_pp'],3) for k,v in blocks.items()},'full_xsoe_vwo_pp':round(full['xsoe_minus_vwo_pp'],3)},sort_keys=True))
