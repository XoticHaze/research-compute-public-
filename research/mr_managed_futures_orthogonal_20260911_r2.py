from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

CANDS=['DBMF','KMLM']; T=CANDS+['BIL','SPY']; START='2020-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_managed_futures_orthogonal_20260911_r2.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=px.resample('ME').last().pct_change().dropna(how='all')
z=m[T].loc['2021-01-01':].dropna()
if len(z)<60: raise SystemExit('SOURCE_COVERAGE_NOT_READY')

def roll12_excess(c):
    cand=(1+z[c]).rolling(12).apply(np.prod,raw=True)*(1-EP)**2-1
    cash=(1+z['BIL']).rolling(12).apply(np.prod,raw=True)-1
    ex=(cand-cash).dropna()
    return {'windows':int(len(ex)),'positive_fraction':float((ex>0).mean()),'median_excess_pp':float(100*ex.median()),'worst_excess_pp':float(100*ex.min())}

def conditional(c,mask):
    q=z.loc[mask,[c,'BIL','SPY']].dropna(); ex=q[c]-q['BIL']
    return {'months':int(len(q)),'candidate_mean_pp':float(100*q[c].mean()),'cash_excess_mean_pp':float(100*ex.mean()),'cash_excess_median_pp':float(100*ex.median()),'positive_excess_fraction':float((ex>0).mean())}

res={}
for c in CANDS:
    res[c]={'rolling12':roll12_excess(c),'spy_down':conditional(c,z['SPY']<0),'spy_severe_down':conditional(c,z['SPY']<=-0.05)}
coverage=all(res[c]['rolling12']['windows']>=48 and res[c]['spy_down']['months']>=20 and res[c]['spy_severe_down']['months']>=5 for c in CANDS)
pass_each={c:(res[c]['rolling12']['positive_fraction']>=0.60 and res[c]['rolling12']['median_excess_pp']>0 and res[c]['spy_down']['cash_excess_mean_pp']>0 and res[c]['spy_severe_down']['cash_excess_mean_pp']>0) for c in CANDS}
passed=coverage and all(pass_each.values())
decision='MANAGED_FUTURES_ORTHOGONAL_ROBUSTNESS_SUPPORTED' if passed else ('MANAGED_FUTURES_ORTHOGONAL_SOURCE_COVERAGE_NOT_READY' if not coverage else 'MANAGED_FUTURES_ORTHOGONAL_ROBUSTNESS_NOT_SUPPORTED')
out={'schema':'research.mr_managed_futures_orthogonal_20260911_r2.v1','workload_id':'MR_MANAGED_FUTURES_ORTHOGONAL_20260911_R2','parent':'MANAGED_FUTURES_DIVERSIFYING_PREMIUM','prior_result':'MR_MANAGED_FUTURES_20260911_R1 failed only the fixed full-sample |SPY correlation| gate for KMLM while both implementations cleared return persistence. This child does not change that gate.','claim':'Without relaxing the failed correlation cap, genuine diversifying managed-futures return evidence should independently persist through rolling 12-month cash excess and conditional SPY-down and severe-down months in both DBMF and KMLM.','contract':{'implementations':CANDS,'history_start':'2021-01','rolling_horizon_months':12,'candidate_endpoint_cost_bps_each_rolling_window':25,'cash_control':'BIL','down_condition':'SPY monthly return < 0','severe_down_condition':'SPY monthly return <= -5%','minimum_positive_rolling12_fraction':0.60,'parameter_search':False},'results':res,'coverage_ready':coverage,'pass_each':pass_each,'decision_rule':'SUPPORTED only if both implementations have >=48 rolling 12m observations, >=60% positive after-cost 12m excess vs BIL with positive median excess, positive mean BIL excess in all SPY-down months, and positive mean BIL excess in severe SPY-down months with >=5 severe observations. This is orthogonal evidence only and does not override R1 correlation-gate failure. No threshold/date/product/cost rescue.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'pass_each':pass_each,'summary':{c:{'roll_pos':round(res[c]['rolling12']['positive_fraction'],3),'roll_med_pp':round(res[c]['rolling12']['median_excess_pp'],3),'down_excess_pp':round(res[c]['spy_down']['cash_excess_mean_pp'],3),'severe_n':res[c]['spy_severe_down']['months'],'severe_excess_pp':round(res[c]['spy_severe_down']['cash_excess_mean_pp'],3)} for c in CANDS}},sort_keys=True))
