from __future__ import annotations
import json
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

T=['CWB','ICVT','SPY','LQD','BIL']
START='2015-01-01'; END='2026-09-12'; EP=.0025
ART=Path('research/artifacts'); ART.mkdir(parents=True,exist_ok=True); OUT=ART/'p562_convertible_convexity_r1.json'
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
c=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
r=c[T].resample('ME').last().pct_change(fill_method=None)

def alpha(sym,start,end=None):
    q=r.loc[start:end,[sym,'SPY','LQD','BIL']].dropna().copy()
    if len(q)<18:return {'months':int(len(q))}
    y=(q[sym]-q.BIL).to_numpy(float).copy(); y[0]-=EP; y[-1]-=EP
    X=np.column_stack([np.ones(len(q)),(q.SPY-q.BIL).to_numpy(float),(q.LQD-q.BIL).to_numpy(float)])
    b=np.linalg.lstsq(X,y,rcond=None)[0]; resid=y-X@b
    return {'months':int(len(q)),'annualized_alpha_pp':float(1200*b[0]),'beta_spy':float(b[1]),'beta_lqd':float(b[2]),'resid_ann_vol':float(np.std(resid,ddof=1)*np.sqrt(12))}

def frame(start,end=None): return {'CWB':alpha('CWB',start,end),'ICVT':alpha('ICVT',start,end)}
windows={'2016+':frame('2016-01-01'),'2020+':frame('2020-01-01'),'2022+':frame('2022-01-01')}
blocks={'2016_2019':frame('2016-01-01','2019-12-31'),'2020_2022':frame('2020-01-01','2022-12-31'),'2023_plus':frame('2023-01-01')}
def count(sym,src): return sum(v[sym].get('months',0)>=18 and v[sym].get('annualized_alpha_pp',-999)>0 for v in src.values())
cw=count('CWB',windows); cb=count('CWB',blocks); iw=count('ICVT',windows); ib=count('ICVT',blocks)
coverage=all(v[s]['months']>=18 for v in blocks.values() for s in ['CWB','ICVT'])
passed=coverage and cw>=2 and cb>=2 and iw>=2 and ib>=2 and windows['2022+']['CWB']['annualized_alpha_pp']>0 and windows['2022+']['ICVT']['annualized_alpha_pp']>0
out={'schema':'research.p562_convertible_convexity_r1.v1','workload_id':'P562_CONVERTIBLE_CONVEXITY_R1','parent':'CONVERTIBLE_BOND_CONVEXITY_ALPHA','claim':'If convertible-bond convexity creates durable fund alpha beyond plain equity and investment-grade credit beta, both CWB and ICVT should retain positive after-cost annualized intercepts versus fixed SPY/LQD factors across long windows and chronology.','contract':{'candidate_endpoint_cost_bps_each':25,'factors':['SPY_minus_BIL','LQD_minus_BIL'],'implementations':['CWB','ICVT'],'windows':['2016+','2020+','2022+'],'blocks':['2016_2019','2020_2022','2023_plus'],'parameter_search':False},'windows':windows,'blocks':blocks,'counts':{'CWB_positive_windows':cw,'CWB_positive_blocks':cb,'ICVT_positive_windows':iw,'ICVT_positive_blocks':ib},'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations have positive annualized intercepts in >=2/3 fixed windows and >=2/3 chronology blocks, both 2022+ alphas are positive, and all blocks have >=18 months. No factor/product/date/cost rescue.','decision':('CONVERTIBLE_CONVEXITY_ALPHA_SUPPORTED' if passed else ('CONVERTIBLE_CONVEXITY_SOURCE_COVERAGE_NOT_READY' if not coverage else 'CONVERTIBLE_CONVEXITY_ALPHA_NOT_SUPPORTED')),'scientific_consequence':('Support cross-implementation convertible convexity alpha beyond broad equity/IG-credit beta; require opportunity-cost and crisis-regime falsification before broader promotion.' if passed else ('Record source coverage insufficiency only.' if not coverage else 'Reject the exact broad convertible convexity-alpha claim without manager/product/factor rescue; preserve any positive subperiods as regime evidence only.')),'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':out['decision'],'counts':out['counts'],'CWB_window_alpha_pp':{k:round(v['CWB']['annualized_alpha_pp'],3) for k,v in windows.items()},'ICVT_window_alpha_pp':{k:round(v['ICVT']['annualized_alpha_pp'],3) for k,v in windows.items()}},sort_keys=True))
