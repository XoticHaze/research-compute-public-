from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
import p82_component_contribution_r2 as p82

START=pd.Timestamp('2015-01-01'); BLOCK=12; DRAWS=5000


def cagr(r):
    r=pd.Series(r,dtype=float).dropna(); return float((1+r).prod()**(12/len(r))-1)


def rolling_excess(c,b,months):
    vals=[]
    for i in range(len(c)-months+1):
        vals.append(cagr(c.iloc[i:i+months])-cagr(b.iloc[i:i+months]))
    a=np.asarray(vals,float)
    return {'window_months':months,'n':len(a),'positive_fraction':float((a>0).mean()),'median_excess_cagr':float(np.median(a)),'p10_excess_cagr':float(np.quantile(a,.1)),'worst_excess_cagr':float(a.min()),'best_excess_cagr':float(a.max())}


def block_bootstrap(excess,seed):
    x=np.asarray(excess,float); n=len(x); starts=np.arange(n-BLOCK+1); rng=np.random.default_rng(seed); vals=[]
    for _ in range(DRAWS):
        parts=[]; size=0
        while size<n:
            s=int(rng.choice(starts)); part=x[s:s+BLOCK]; parts.append(part); size+=len(part)
        y=np.concatenate(parts)[:n]; vals.append(float(y.mean()*12))
    a=np.asarray(vals,float); lo,hi=np.quantile(a,[.025,.975])
    return {'block_months':BLOCK,'draws':DRAWS,'annualized_mean_excess':float(x.mean()*12),'bootstrap_95pct':[float(lo),float(hi)],'p_excess_le_zero':float((a<=0).mean())}


def main():
    f=p82.build().loc[START:].copy()
    candidate=0.5*f.p64+0.5*f.p36
    matched=0.5*f.p64_matched+0.5*f.p36_matched
    tests={}
    for name,b in [('matched',matched),('qqq',f.qqq)]:
        tests[name]={
          'rolling_36m':rolling_excess(candidate,b,36),
          'rolling_60m':rolling_excess(candidate,b,60),
          'moving_block_bootstrap':block_bootstrap(candidate-b,82 if name=='matched' else 182),
          'full_excess_cagr':cagr(candidate)-cagr(b)
        }
    support=(tests['matched']['rolling_60m']['positive_fraction']>=0.70 and tests['matched']['moving_block_bootstrap']['p_excess_le_zero']<=0.10 and tests['qqq']['rolling_60m']['positive_fraction']>=0.60 and tests['qqq']['moving_block_bootstrap']['p_excess_le_zero']<=0.15)
    out={
      'schema':'research.p82_serial_persistence_r1','parent':'P82',
      'hypothesis':'The unchanged fixed 50/50 P64+P36 blend has post-2015 after-cost excess that is persistent across contiguous multi-year windows and survives serial-dependence-aware uncertainty against both the exact matched control and QQQ.',
      'scientific_contract':{'blend_weights':[0.5,0.5],'component_cost_bps':50,'start':'2015-01-01','rolling_windows_months':[36,60],'moving_block_months':BLOCK,'bootstrap_draws':DRAWS,'comparators':['same fixed component matched-control blend','QQQ'],'no_parameter_or_weight_tuning':True},
      'tests':tests,
      'decision':'P82_SERIAL_PERSISTENCE_SUPPORTED' if support else 'P82_SERIAL_PERSISTENCE_WEAK'
    }
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p82_serial_persistence_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
