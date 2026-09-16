from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

T = ['QAI', 'SPY', 'BIL']
EP = 0.0025
x = yf.download(T, start='2010-01-01', end='2026-09-11', auto_adjust=True, progress=False, threads=False)
if x.empty:
    raise SystemExit('SOURCE_FAILURE_EMPTY')
c = x['Close'] if isinstance(x.columns, pd.MultiIndex) else x
missing = [t for t in T if t not in c.columns]
if missing:
    raise SystemExit('SOURCE_FAILURE_MISSING_' + '_'.join(missing))
r = c[T].resample('ME').last().dropna().pct_change(fill_method=None).dropna()

def ep(s):
    y=s.copy()
    if len(y):
        y.iloc[0]-=EP; y.iloc[-1]-=EP
    return y

def stats(s):
    q=ep(s.dropna()); n=len(q)
    if n<3: return {'months':n,'cagr':None,'sharpe':None,'max_drawdown':None}
    w=(1+q).cumprod(); vol=q.std(ddof=1)*math.sqrt(12); ann=q.mean()*12
    return {'months':n,'cagr':float(w.iloc[-1]**(12/n)-1),'sharpe':float(ann/vol) if vol else None,'max_drawdown':float((w/w.cummax()-1).min())}

def reg(q):
    y=q.QAI-q.BIL; z=q.SPY-q.BIL
    X=np.column_stack([np.ones(len(q)),z.values]); a,b=np.linalg.lstsq(X,y.values,rcond=None)[0]
    return {'months':len(q),'beta':float(b),'alpha_pp_annual':float(1200*a)}

def ev(a,b=None):
    q=r.loc[a:b].dropna(); s=stats(q.QAI); cash=stats(q.BIL); spy=stats(q.SPY); rr=reg(q)
    return {'qai':s,'cash_control':cash,'spy_opportunity':spy,'regression':rr,
            'cash_cagr_excess_pp':100*(s['cagr']-cash['cagr']),
            'spy_cagr_opportunity_pp':100*(s['cagr']-spy['cagr'])}

windows={k:ev(v) for k,v in {'2011+':'2011-01-01','2016+':'2016-01-01','2020+':'2020-01-01'}.items()}
blocks={k:ev(a,b) for k,(a,b) in {
 '2011_2013':('2011-01-01','2013-12-31'),
 '2014_2017':('2014-01-01','2017-12-31'),
 '2018_2020':('2018-01-01','2020-12-31'),
 '2021_2023':('2021-01-01','2023-12-31'),
 '2024_plus':('2024-01-01',None)}.items()}
pos_alpha=sum(z['regression']['alpha_pp_annual']>0 for z in blocks.values())
pos_cash=sum(z['cash_cagr_excess_pp']>0 for z in blocks.values())
supported=(all(z['regression']['alpha_pp_annual']>0 for z in windows.values()) and
           all(z['cash_cagr_excess_pp']>0 for z in windows.values()) and
           pos_alpha>=4 and pos_cash>=4)
decision='ALT_RISK_PREMIA_ALPHA_SUPPORTED' if supported else 'ALT_RISK_PREMIA_ALPHA_NOT_SUPPORTED'
out={
 'schema':'research.p434_qai_alt_risk_premia_alpha_r1.v1',
 'workload_id':'P434_QAI_ALT_RISK_PREMIA_ALPHA_R1',
 'parent':'ALTERNATIVE_RISK_PREMIA_ALPHA',
 'claim':'A prospectively fixed alternative-risk-premia fund representation (QAI) can deliver durable after-cost cash excess and beta-adjusted alpha; SPY opportunity cost is reported separately so diversification or low beta cannot itself count as alpha.',
 'cost_bps_each_endpoint':25,
 'windows':windows,
 'chronology_blocks':blocks,
 'positive_alpha_blocks':pos_alpha,
 'positive_cash_excess_blocks':pos_cash,
 'decision_rule':'SUPPORTED only if annualized Jensen alpha and cash CAGR excess are positive in 2011+/2016+/2020+ and >=4/5 fixed chronology blocks are positive for both. No fund/date/beta/cost/threshold rescue.',
 'decision':decision,
 'scientific_consequence':('Alternative risk premia earns initial scoped support requiring independent implementation or residual-source validation.' if supported else 'Reject this exact QAI alternative-risk-premia alpha claim while preserving any passing eras; do not rescue with another product, dates, beta model, costs, or thresholds.'),
 'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p434_qai_alt_risk_premia_alpha_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps({'decision':decision,'positive_alpha_blocks':pos_alpha,'positive_cash_excess_blocks':pos_cash,'window_alpha_pp':{k:round(v['regression']['alpha_pp_annual'],3) for k,v in windows.items()},'window_cash_excess_pp':{k:round(v['cash_cagr_excess_pp'],3) for k,v in windows.items()},'block_alpha_pp':{k:round(v['regression']['alpha_pp_annual'],3) for k,v in blocks.items()}},sort_keys=True))
