from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import p273_industry_capital_role_cost_stress_r1 as p273

WINDOWS={'2020':'2020-01-01','2022':'2022-01-01'}

def metrics(r):
    q=pd.Series(r,dtype=float).dropna()
    e=(1+q).cumprod(); n=len(q)
    ann=float(q.mean()*12); vol=float(q.std(ddof=1)*math.sqrt(12))
    return {'months':int(n),'cagr':float(e.iloc[-1]**(12/n)-1),'maxdd':float((e/e.cummax()-1).min()),'sharpe_rf0':float(ann/vol) if vol else None}

def worst12(r):
    q=pd.Series(r,dtype=float).dropna()
    roll=(1+q).rolling(12).apply(np.prod,raw=True)-1
    return float(roll.min()) if roll.notna().any() else None

out={}
for name,start in WINDOWS.items():
    q=p273.x.loc[p273.x.index>=pd.Timestamp(start)].copy()
    full=p273.ep((q.sv+q.p64+q.p36+q.ind)/4,p273.SV_BP/4)
    base=p273.ep((q.sv+q.p64+q.p36)/3,p273.SV_BP/3)
    delta=full-base
    neg=base<0
    tail=base<=base.quantile(0.25)
    neg_delta=delta.loc[neg]
    tail_delta=delta.loc[tail]
    fm,bm=metrics(full),metrics(base)
    out[name]={
        'full':fm,
        'p249_base':bm,
        'maxdd_delta':fm['maxdd']-bm['maxdd'],
        'worst_12m_full':worst12(full),
        'worst_12m_p249':worst12(base),
        'worst_12m_delta':worst12(full)-worst12(base),
        'p249_negative_months':int(neg.sum()),
        'negative_month_mean_return_delta':float(neg_delta.mean()),
        'negative_month_median_return_delta':float(neg_delta.median()),
        'negative_month_improvement_hit_rate':float((neg_delta>0).mean()),
        'p249_worst_quartile_months':int(tail.sum()),
        'worst_quartile_mean_return_delta':float(tail_delta.mean()),
        'worst_quartile_improvement_hit_rate':float((tail_delta>0).mean())
    }

checks=[]
for z in out.values():
    checks += [
        z['maxdd_delta']>0,
        z['worst_12m_delta']>0,
        z['negative_month_mean_return_delta']>0,
        z['worst_quartile_mean_return_delta']>0,
    ]
passed=sum(checks)
if passed>=7:
    decision='P274_DOWNSIDE_ROLE_SUPPORTED'
elif passed>=4:
    decision='P274_DOWNSIDE_ROLE_MIXED'
else:
    decision='P274_DOWNSIDE_ROLE_NOT_SUPPORTED_DIMENSION'

res={
    'schema':'research.p274_industry_downside_role_r1',
    'parent':'P266/P272/P273/P274',
    'claim':'With P273 specification frozen, test whether adding the P266 industry sleeve improves downside behavior relative to fixed P249 in P249-negative months, P249 worst-quartile months, max drawdown, and worst rolling 12-month return.',
    'contract':{
        'source_spec':'P273 unchanged: equal-quarter P249+P266, industry turnover cost 50 bps, no signal/weight/lookback/universe changes',
        'windows':WINDOWS,
        'downside_condition':'months where fixed P249 monthly return < 0',
        'tail_condition':'bottom quartile of fixed P249 monthly returns within each predeclared window',
        'decision_rule':'SUPPORTED if >=7/8 directional checks pass; MIXED if 4-6/8 pass; otherwise NOT_SUPPORTED_DIMENSION. This adjudicates only the downside-risk-role dimension and does not kill prior supported evidence.'
    },
    'tests':out,
    'directional_checks_passed':passed,
    'directional_checks_total':len(checks),
    'decision':decision,
    'limitations':['Yahoo adjusted prices research-only','tail quartile is a fixed descriptive stress slice, not a tuned trading rule','scientific risk-role evidence only; no portfolio allocation/ranking authority'],
    'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}
}
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/p274_industry_downside_role_r1.json').write_text(json.dumps(res,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps(res,sort_keys=True))
