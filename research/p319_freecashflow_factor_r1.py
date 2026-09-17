from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

PAIRS={'COWZ_VTI':('COWZ','VTI'),'CALF_IJR':('CALF','IJR')}
SYMS=sorted({s for pair in PAIRS.values() for s in pair})
START='2017-01-01'; END='2026-09-10'; COST_BPS=10
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS]

def stats(s):
    s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std()
    return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}

def evaluate(qsym,bsym):
    p=px[[qsym,bsym]].dropna().resample('ME').last().pct_change().dropna(); q=p[qsym].copy(); b=p[bsym].copy(); q.iloc[0]-=COST_BPS/10000
    results={}
    for name,start in {'2018_plus':'2018-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items():
        z=pd.DataFrame({'q':q,'b':b}).loc[start:].dropna(); qs,bs=stats(z.q),stats(z.b); results[name]={'factor':qs,'matched':bs,'matched_excess_cagr':qs['cagr']-bs['cagr']}
    z=pd.DataFrame({'q':q,'b':b}).loc['2018-01-01':].dropna(); folds=[stats(f.q)['cagr']-stats(f.b)['cagr'] for f in np.array_split(z,5)]
    passed=all(results[k]['matched_excess_cagr']>0 for k in results) and sum(v>0 for v in folds)>=3
    return {'factor':qsym,'matched':bsym,'results':results,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(v>0 for v in folds),'passed':passed}

pairs={name:evaluate(*pair) for name,pair in PAIRS.items()}
passes=sum(v['passed'] for v in pairs.values())
if passes==2: decision='P319_FREECASHFLOW_FACTOR_FAMILY_SUPPORTED'
elif passes==1: decision='P319_FREECASHFLOW_FACTOR_REPRESENTATION_CONDITIONAL'
else: decision='P319_FREECASHFLOW_FACTOR_NOT_SUPPORTED'
out={'schema':'research.p319_freecashflow_factor_r1','parent':'P319','claim':'Test a materially distinct cash-generation/value-selection family using two predeclared free-cash-flow ETF representations: COWZ vs VTI and CALF vs IJR, each after 10bp entry friction, fixed 2018+/2020+/2022+ windows and five chronology folds. No product, weighting, window, or factor-definition search.','cost_bps':COST_BPS,'pairs':pairs,'decision_rule':'Broad family support requires BOTH representations to have positive matched excess CAGR in every fixed window and >=3/5 positive chronology folds. One pass is representation-conditional evidence only; two failures reject this nearby ETF family without rescue.','decision':decision,'limitations':['ETF-level economic proxy, not constituent-level causal proof','common Pacer free-cash-flow methodology family means representations are size-separated rather than provider-independent','same adjusted-price provider','no product/factor/window rescue','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True)
Path('research/artifacts/p319_freecashflow_factor_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
print(json.dumps(out,sort_keys=True))
