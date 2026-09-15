from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

CANDS=['SPLV','USMV']; T=CANDS+['SPY','BIL']; START='2008-01-01'; END='2026-09-12'; EP=.0025
OUT=Path('research/artifacts/mr_lowvol_beta_matched_20260911_r1.json'); OUT.parent.mkdir(parents=True,exist_ok=True)
raw=yf.download(T,start=START,end=END,auto_adjust=True,progress=False,threads=False)
if raw.empty: raise SystemExit('SOURCE_FAILURE_EMPTY')
px=raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw
m=px.resample('ME').last().pct_change().dropna(how='all')

def wealth_stats(r: pd.Series, endpoint_cost: float=0.0):
    r=r.dropna()
    if len(r)<18:return {'months':int(len(r))}
    wealth=(1+r).cumprod()
    if endpoint_cost:
        wealth=wealth*(1-endpoint_cost)**2
    years=len(r)/12.0
    cagr=float(wealth.iloc[-1]**(1/years)-1)
    dd=wealth/wealth.cummax()-1
    vol=float(r.std(ddof=1)*math.sqrt(12))
    sh=float((r.mean()/r.std(ddof=1))*math.sqrt(12)) if r.std(ddof=1)>0 else float('nan')
    return {'months':int(len(r)),'cagr':cagr,'maxdd':float(dd.min()),'vol':vol,'sharpe':sh}

def pair(sym: str):
    z=m[[sym,'SPY','BIL']].dropna().copy()
    cov=z[sym].rolling(24,min_periods=24).cov(z['SPY']).shift(1)
    var=z['SPY'].rolling(24,min_periods=24).var().shift(1)
    beta=(cov/var).replace([np.inf,-np.inf],np.nan)
    z['beta_lag24']=beta
    z['matched']=z['beta_lag24']*z['SPY']+(1-z['beta_lag24'])*z['BIL']
    return z.dropna(subset=['beta_lag24','matched'])

series={s:pair(s) for s in CANDS}
windows={'2014+':('2014-01-01',None),'2016+':('2016-01-01',None),'2020+':('2020-01-01',None),'2022+':('2022-01-01',None)}
blocks={'2014_2016':('2014-01-01','2016-12-31'),'2017_2019':('2017-01-01','2019-12-31'),'2020_2022':('2020-01-01','2022-12-31'),'2023_plus':('2023-01-01',None)}

def evaluate(sym,start,end=None):
    z=series[sym].loc[start:end]
    cs=wealth_stats(z[sym],EP); bs=wealth_stats(z['matched'],0.0); spy=wealth_stats(z['SPY'],0.0)
    out={'candidate':cs,'beta_matched_control':bs,'spy_opportunity':spy,'beta_mean':float(z['beta_lag24'].mean()) if len(z) else None}
    if cs.get('months',0)>=18 and bs.get('months',0)>=18:
        out['matched_excess_cagr_pp']=100*(cs['cagr']-bs['cagr'])
        out['spy_excess_cagr_pp']=100*(cs['cagr']-spy['cagr'])
        out['drawdown_improvement_pp']=100*(cs['maxdd']-bs['maxdd'])
    return out

res={'windows':{},'blocks':{}}
for label,(a,b) in windows.items(): res['windows'][label]={s:evaluate(s,a,b) for s in CANDS}
for label,(a,b) in blocks.items(): res['blocks'][label]={s:evaluate(s,a,b) for s in CANDS}

def positive_count(kind,sym): return sum(v[sym].get('matched_excess_cagr_pp',-999)>0 for v in res[kind].values())
counts={s:{'positive_windows':positive_count('windows',s),'positive_blocks':positive_count('blocks',s)} for s in CANDS}
coverage=all(v[s]['candidate'].get('months',0)>=18 for v in res['blocks'].values() for s in CANDS)
recent=all(res['windows']['2022+'][s].get('matched_excess_cagr_pp',-999)>0 for s in CANDS)
full_dd=all(res['windows']['2014+'][s].get('drawdown_improvement_pp',-999)>0 for s in CANDS)
passed=coverage and recent and full_dd and all(counts[s]['positive_windows']>=3 and counts[s]['positive_blocks']>=3 for s in CANDS)
decision='LOWVOL_BETA_MATCHED_PREMIUM_SUPPORTED' if passed else ('LOWVOL_SOURCE_COVERAGE_NOT_READY' if not coverage else 'LOWVOL_BETA_MATCHED_PREMIUM_NOT_SUPPORTED')
out={'schema':'research.mr_lowvol_beta_matched_20260911_r1.v1','workload_id':'MR_LOWVOL_BETA_MATCHED_20260911_R1','parent':'LOW_VOLATILITY_EQUITY_PREMIUM','claim':'If investable low-volatility equity selection creates durable excess beyond simple market-beta reduction, both SPLV and USMV should beat their own one-month-lagged 24-month beta-matched SPY+BIL controls after fixed endpoint costs across fixed windows and disjoint chronology, while improving full-history drawdown.','contract':{'implementations':CANDS,'matched_control':'candidate-specific one-month-lagged 24-month beta * SPY + (1-beta) * BIL','opportunity_control':'SPY','candidate_endpoint_cost_bps_each':25,'control_cost_bps':0,'beta_estimation_months':24,'parameter_search':False,'windows':list(windows),'blocks':list(blocks)},**res,'counts':counts,'coverage_ready':coverage,'decision_rule':'SUPPORTED only if both implementations have positive beta-matched after-cost CAGR excess in >=3/4 fixed windows and >=3/4 blocks, both are positive from 2022+, both improve max drawdown versus beta-matched control over 2014+, and each block has >=18 months. No product/control/beta-window/date/cost rescue.','decision':decision,'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
OUT.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'counts':counts,'2014+':{s:{'matched_excess_pp':round(res['windows']['2014+'][s].get('matched_excess_cagr_pp',-999),3),'spy_excess_pp':round(res['windows']['2014+'][s].get('spy_excess_cagr_pp',-999),3),'dd_improve_pp':round(res['windows']['2014+'][s].get('drawdown_improvement_pp',-999),3),'beta':round(res['windows']['2014+'][s].get('beta_mean') or -999,3)} for s in CANDS},'2022+':{s:round(res['windows']['2022+'][s].get('matched_excess_cagr_pp',-999),3) for s in CANDS}},sort_keys=True))
