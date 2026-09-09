from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import p82_component_contribution_r2 as p82

WEIGHTS=(0.25,0.50,0.75)
WINDOWS={'full':('2005-01-01',None),'pre2015':('2005-01-01','2014-12-31'),'2015_forward':('2015-01-01',None),'2022_forward':('2022-01-01',None)}


def cagr(r):
    r=pd.Series(r,dtype=float).dropna()
    return float((1+r).prod()**(12/len(r))-1) if len(r) else float('nan')


def risk(r):
    r=pd.Series(r,dtype=float).dropna(); eq=(1+r).cumprod(); vol=float(r.std(ddof=1)*math.sqrt(12)); ann=float(r.mean()*12)
    return {'cagr':cagr(r),'max_drawdown':float((eq/eq.cummax()-1).min()),'annualized_vol':vol,'sharpe_rf0':ann/vol if vol else None}


def score(q,w64):
    w36=1.0-w64
    cand=w64*q.p64+w36*q.p36
    matched=w64*q.p64_matched+w36*q.p36_matched
    folds=[]
    for i,ids in enumerate(np.array_split(np.arange(len(q)),5),1):
        z=q.iloc[ids]
        if not len(z): continue
        c=w64*z.p64+w36*z.p36; m=w64*z.p64_matched+w36*z.p36_matched
        folds.append({'fold':i,'excess_vs_matched':cagr(c)-cagr(m),'excess_vs_qqq':cagr(c)-cagr(z.qqq)})
    return {
        'months':len(q),'p64_weight':w64,'p36_weight':w36,
        'candidate':risk(cand),'matched':risk(matched),'qqq':risk(q.qqq),
        'excess_cagr_vs_matched':cagr(cand)-cagr(matched),
        'excess_cagr_vs_qqq':cagr(cand)-cagr(q.qqq),
        'positive_folds_vs_matched':sum(x['excess_vs_matched']>0 for x in folds),
        'positive_folds_vs_qqq':sum(x['excess_vs_qqq']>0 for x in folds),
        'folds':folds,
    }


def main():
    f=p82.build(); tests={}
    for label,(start,end) in WINDOWS.items():
        q=f.loc[f.index>=pd.Timestamp(start)]
        if end: q=q.loc[q.index<=pd.Timestamp(end)]
        tests[label]={str(w):score(q,w) for w in WEIGHTS}
    inv=[]
    for w in WEIGHTS:
        a=tests['2015_forward'][str(w)]; b=tests['2022_forward'][str(w)]
        inv.append(a['excess_cagr_vs_matched']>0 and a['positive_folds_vs_matched']>=3 and b['excess_cagr_vs_matched']>0 and b['positive_folds_vs_matched']>=3)
    out={
      'schema':'research.p82_weight_invariance_r1','parent':'P82',
      'hypothesis':'The supported P64+P36 complementarity is not an artifact of the exact 50/50 sleeve weight; a prospectively fixed coarse weight set preserves matched-control excess without selecting a best weight.',
      'scientific_contract':{
        'p64_weights':list(WEIGHTS),'p36_weight':'1-p64_weight','component_economics':'unchanged P64 and P36 components, each already net of frozen 50 bps costs','windows':WINDOWS,
        'comparators':['same-weight blend of component matched controls','QQQ'],'chronological_folds':5,
        'decision_uses':['2015_forward matched excess','2022_forward matched excess'],'no_weight_selection_or_tuning':True
      },
      'tests':tests,
      'decision':'P82_WEIGHT_INVARIANCE_SUPPORTED' if all(inv) else 'P82_WEIGHT_SENSITIVE'
    }
    Path('artifacts').mkdir(exist_ok=True); Path('artifacts/p82_weight_invariance_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    print(json.dumps(out,sort_keys=True))

if __name__=='__main__': main()
