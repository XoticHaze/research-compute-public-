from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['FLRN','FLOT','HYG','SHV','BIL']
START='2012-01-01'; END='2026-09-12'; EP=.0025
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True); OUT=ART/'p561_floating_rate_credit_alpha_r1.json'
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None)

def alpha(sym,start,end=None):
    q=r.loc[start:end,[sym,'HYG','SHV','BIL']].dropna().copy()
    if len(q)<18:return {'months':int(len(q))}
    y=(q[sym]-q.BIL).to_numpy(float)
    y[0]-=EP; y[-1]-=EP
    X=np.column_stack([np.ones(len(q)),(q.HYG-q.BIL).to_numpy(float),(q.SHV-q.BIL).to_numpy(float)])
    b=np.linalg.lstsq(X,y,rcond=None)[0]
    resid=y-X@b
    return {'months':int(len(q)),'annualized_alpha_pp':float(1200*b[0]),'beta_hyg':float(b[1]),'beta_shv':float(b[2]),'resid_ann_vol':float(np.std(resid,ddof=1)*np.sqrt(12))}

def frame(start,end=None):return {'FLRN':alpha('FLRN',start,end),'FLOT':alpha('FLOT',start,end)}
windows={'2013+':frame('2013-01-01'),'2018+':frame('2018-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2013_2016':frame('2013-01-01','2016-12-31'),'2017_2020':frame('2017-01-01','2020-12-31'),'2021_2023':frame('2021-01-01','2023-12-31'),'2024_plus':frame('2024-01-01')}
def count(sym,src):return sum(v[sym].get('months',0)>=18 and v[sym].get('annualized_alpha_pp',-999)>0 for v in src.values())
fw=count('FLRN',windows); fb=count('FLRN',blocks); tw=count('FLOT',windows); tb=count('FLOT',blocks)
coverage=all(v[s]['months']>=18 for v in blocks.values() for s in ['FLRN','FLOT'])
recent=windows['2022+']['FLRN']['annualized_alpha_pp']>0 and windows['2022+']['FLOT']['annualized_alpha_pp']>0
passed=coverage and fw>=3 and fb>=3 and tw>=3 and tb>=3 and recent
out={'schema':'research.p561_floating_rate_credit_alpha_r1.v1','workload_id':'P561_FLOATING_RATE_CREDIT_ALPHA_R1','parent':'FLOATING_RATE_IG_CREDIT_CARRY','claim':'If P560 excess is more than broad credit-beta compensation, both FLRN and FLOT should retain positive after-cost annualized intercepts after fixed HYG and SHV excess-return attribution across long windows and chronology blocks.','contract':{'candidate_endpoint_cost_bps_each':25,'factors':['HYG_minus_BIL','SHV_minus_BIL'],'windows':['2013+','2018+','2020+','2022+'],'blocks':['2013_2016','2017_2020','2021_2023','2024_plus'],'parameter_search':False},'windows':windows,'blocks':blocks,'counts':{'FLRN_positive_alpha_windows':fw,'FLRN_positive_alpha_blocks':fb,'FLOT_positive_alpha_windows':tw,'FLOT_positive_alpha_blocks':tb},'coverage_ready':coverage,'decision_rule':'INDEPENDENT_ALPHA_SUPPORTED only if both implementations have positive annualized intercepts in >=3/4 fixed windows and >=3/4 chronology blocks, both 2022+ intercepts are positive, and all blocks have >=18 months. No factor/product/date/cost rescue.','decision':('FLOATING_RATE_IG_INDEPENDENT_ALPHA_SUPPORTED' if passed else ('FLOATING_RATE_IG_ALPHA_SOURCE_COVERAGE_NOT_READY' if not coverage else 'FLOATING_RATE_IG_INDEPENDENT_ALPHA_NOT_SUPPORTED')),'scientific_consequence':('Strengthen P560 from robust carry to cross-implementation credit-beta-adjusted alpha; still require opportunity-cost/portfolio-fit testing outside Market Research allocation authority.' if passed else ('Record attribution-data insufficiency only; preserve P560 raw carry evidence.' if not coverage else 'Preserve P560 durable floating-rate carry but classify it as broad-credit-compensation-consistent rather than independent alpha; do not change factors/products/dates to rescue.')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'FLRN_window_alpha_pp':{k:round(v['FLRN']['annualized_alpha_pp'],3) for k,v in windows.items()},'FLOT_window_alpha_pp':{k:round(v['FLOT']['annualized_alpha_pp'],3) for k,v in windows.items()}},sort_keys=True))
