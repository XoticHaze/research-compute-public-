from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

PAIRS={'XYLD':'SPY','QYLD':'QQQ'}; T=['XYLD','QYLD','SPY','QQQ','BIL']; START='2010-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_covered_call_beta_matched_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=px.resample('ME').last().pct_change().dropna(how='all')

def stats(r,cost=0.0):
    r=r.dropna()
    if len(r)<18:return {'months':int(len(r))}
    w=(1+r).cumprod()*(1-cost)**2; years=len(r)/12.0
    dd=w/w.cummax()-1; sd=r.std(ddof=1)
    return {'months':int(len(r)),'cagr':float(w.iloc[-1]**(1/years)-1),'maxdd':float(dd.min()),'sharpe':float((r.mean()/sd)*math.sqrt(12)) if sd>0 else None}

def pair(cand,under):
    z=m[[cand,under,'BIL']].dropna().copy()
    beta=z[cand].rolling(24,min_periods=24).cov(z[under]).shift(1)/z[under].rolling(24,min_periods=24).var().shift(1)
    z['beta']=beta.replace([np.inf,-np.inf],np.nan)
    z['matched']=z['beta']*z[under]+(1-z['beta'])*z['BIL']
    return z.dropna()
series={c:pair(c,u) for c,u in PAIRS.items()}
windows={'2016+':('2016-01-01',None),'2018+':('2018-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2016_2018':('2016-01-01','2018-12-31'),'2019_2021':('2019-01-01','2021-12-31'),'2022_2023':('2022-01-01','2023-12-31'),'2024_plus':('2024-01-01',None)}

def eval_one(c,a,b=None):
    u=PAIRS[c]; z=series[c].loc[a:b]; cs=stats(z[c],EP); bs=stats(z['matched']); us=stats(z[u])
    out={'candidate':cs,'beta_matched_control':bs,'underlying_opportunity':us,'beta_mean':float(z['beta'].mean()) if len(z) else None}
    if cs.get('months',0)>=18 and bs.get('months',0)>=18:
        out['matched_excess_cagr_pp']=100*(cs['cagr']-bs['cagr']); out['underlying_excess_cagr_pp']=100*(cs['cagr']-us['cagr']); out['drawdown_improvement_pp']=100*(cs['maxdd']-bs['maxdd'])
    return out
res={'windows':{},'blocks':{}}
for k,(a,b) in windows.items():res['windows'][k]={c:eval_one(c,a,b) for c in PAIRS}
for k,(a,b) in blocks.items():res['blocks'][k]={c:eval_one(c,a,b) for c in PAIRS}
def cnt(kind,c):return sum(v[c].get('matched_excess_cagr_pp',-999)>0 for v in res[kind].values())
counts={c:{'positive_windows':cnt('windows',c),'positive_blocks':cnt('blocks',c)} for c in PAIRS}
coverage=all(v[c]['candidate'].get('months',0)>=18 for v in res['blocks'].values() for c in PAIRS)
recent=all(res['windows']['2022+'][c].get('matched_excess_cagr_pp',-999)>0 for c in PAIRS)
passed=coverage and recent and all(counts[c]['positive_windows']>=3 and counts[c]['positive_blocks']>=3 for c in PAIRS)
decision='COVERED_CALL_BETA_MATCHED_PREMIUM_SUPPORTED' if passed else ('COVERED_CALL_SOURCE_COVERAGE_NOT_READY' if not coverage else 'COVERED_CALL_BETA_MATCHED_PREMIUM_NOT_SUPPORTED')
out={'schema':'research.mr_covered_call_beta_matched_20260911_r1.v1','workload_id':'MR_COVERED_CALL_BETA_MATCHED_20260911_R1','parent':'COVERED_CALL_OPTION_PREMIUM','claim':'If systematic covered-call funds create durable option-premium excess beyond their reduced equity beta, both XYLD and QYLD should beat one-month-lagged 24-month beta-matched underlying+BIL controls after fixed endpoint costs across fixed windows and disjoint chronology.','contract':{'implementations':PAIRS,'matched_control':'candidate-specific lagged-24m beta * underlying + (1-beta) * BIL','candidate_endpoint_cost_bps_each':25,'control_cost_bps':0,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},**res,'counts':counts,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations have positive beta-matched after-cost CAGR excess in >=3/4 windows and >=3/4 chronology blocks, both positive from 2022+, and every block has >=18 months. No product/control/beta-window/date/cost rescue.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'counts':counts,'full':{c:{'matched_excess_pp':round(res['windows']['2016+'][c].get('matched_excess_cagr_pp',-999),3),'underlying_excess_pp':round(res['windows']['2016+'][c].get('underlying_excess_cagr_pp',-999),3),'beta':round(res['windows']['2016+'][c].get('beta_mean') or -999,3)} for c in PAIRS},'2022+':{c:round(res['windows']['2022+'][c].get('matched_excess_cagr_pp',-999),3) for c in PAIRS}},sort_keys=True))
