from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['ITA','PPA','XLI','SPY']
START='2009-01-01'; END='2026-09-12'; EP=.0025
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True); OUT=ART/'p563_defense_industry_r1.json'
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None)

def stats(s):
    x=s.dropna().astype(float)
    if len(x)<12:return {'months':int(len(x))}
    y=x.to_numpy(float).copy(); y[0]-=EP; y[-1]-=EP
    w=np.cumprod(1+y); yrs=len(y)/12
    cagr=float(w[-1]**(1/yrs)-1); vol=float(np.std(y,ddof=1)*math.sqrt(12)); sh=float(np.mean(y)*12/vol) if vol>0 else None
    dd=float(np.min(w/np.maximum.accumulate(w)-1))
    return {'months':int(len(y)),'cagr':cagr,'vol':vol,'sharpe':sh,'max_drawdown':dd}

def frame(start,end=None):
    q=r.loc[start:end,T].dropna(); x=stats(q.XLI); sp=stats(q.SPY); out={'months':int(len(q)),'xli':x,'spy':sp}
    for sym in ['ITA','PPA']:
        s=stats(q[sym]); out[sym.lower()]=s; out[sym.lower()+'_minus_xli_pp']=100*(s['cagr']-x['cagr']); out[sym.lower()+'_minus_spy_pp']=100*(s['cagr']-sp['cagr'])
    return out
windows={'2010+':frame('2010-01-01'),'2015+':frame('2015-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2010_2014':frame('2010-01-01','2014-12-31'),'2015_2019':frame('2015-01-01','2019-12-31'),'2020_2022':frame('2020-01-01','2022-12-31'),'2023_plus':frame('2023-01-01')}
def count(sym,src):
    k=sym.lower()+'_minus_xli_pp'; return sum(v['months']>=24 and v[k]>0 for v in src.values())
iw=count('ITA',windows); ib=count('ITA',blocks); pw=count('PPA',windows); pb=count('PPA',blocks)
coverage=all(v['months']>=24 for v in blocks.values())
recent=windows['2022+']['ita_minus_xli_pp']>0 and windows['2022+']['ppa_minus_xli_pp']>0
passed=coverage and iw>=3 and ib>=3 and pw>=3 and pb>=3 and recent
out={'schema':'research.p563_defense_industry_r1.v1','workload_id':'P563_DEFENSE_INDUSTRY_R1','parent':'DEFENSE_AEROSPACE_INDUSTRY_PREMIUM','claim':'Defense/aerospace industry exposure should deliver durable after-cost excess versus broad industrials XLI across two independent fund implementations; SPY is opportunity context only.','contract':{'endpoint_cost_bps_each':25,'implementations':['ITA','PPA'],'matched_control':'XLI','windows':['2010+','2015+','2020+','2022+'],'blocks':['2010_2014','2015_2019','2020_2022','2023_plus'],'parameter_search':False},'windows':windows,'blocks':blocks,'counts':{'ITA_positive_windows':iw,'ITA_positive_blocks':ib,'PPA_positive_windows':pw,'PPA_positive_blocks':pb},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both ITA and PPA have positive after-cost CAGR excess versus XLI in >=3/4 fixed windows and >=3/4 chronology blocks, both are positive in 2022+, and every block has >=24 months. No alternate fund/control/date/cost rescue.','decision':('DEFENSE_INDUSTRY_PREMIUM_SUPPORTED' if passed else ('DEFENSE_INDUSTRY_SOURCE_COVERAGE_NOT_READY' if not coverage else 'DEFENSE_INDUSTRY_PREMIUM_NOT_SUPPORTED')),'scientific_consequence':('Support a cross-implementation defense/aerospace industry premium relative to broad industrials; next falsifier should separate sustained industry economics from recent geopolitical/regime concentration before broader promotion.' if passed else ('Record source coverage insufficiency only.' if not coverage else 'Reject the exact broad defense-industry durable-premium claim without product/control/date rescue; preserve passing subperiods as regime evidence only.')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'ITA_windows_pp':{k:round(v['ita_minus_xli_pp'],3) for k,v in windows.items()},'PPA_windows_pp':{k:round(v['ppa_minus_xli_pp'],3) for k,v in windows.items()}},sort_keys=True))
