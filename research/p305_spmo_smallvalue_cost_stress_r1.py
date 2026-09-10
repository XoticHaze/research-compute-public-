from __future__ import annotations
import json
from pathlib import Path
import pandas as pd, numpy as np, yfinance as yf
SYMS=['SPMO','SPY','IJS','IJR']; START='2015-01-01'; END='2026-09-10'; COSTS=[10,25,50]
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False); px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna(); m=px.resample('ME').last().pct_change().dropna(); gross=.5*m.SPMO+.5*m.IJS; drift=.5*(1+m.SPMO)/(1+gross); turnover=2*(drift-.5).abs(); bench=.5*m.SPY+.5*m.IJR

def cagr(s): s=s.dropna(); return float((1+s).prod()**(12/len(s))-1)
def one(cost,start):
 n=(gross-turnover*(cost/10000)).loc[start:]; b=bench.loc[n.index]; return cagr(n)-cagr(b)
res={}; ok=True
for c in COSTS:
 windows={k:one(c,v) for k,v in {'2017_plus':'2017-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items()}; z=pd.DataFrame({'n':gross-turnover*(c/10000),'b':bench}).loc['2017-01-01':].dropna(); folds=[cagr(p.n)-cagr(p.b) for p in np.array_split(z,5)]; res[str(c)]={'matched_excess_cagr':windows,'positive_folds':sum(x>0 for x in folds),'folds':folds}; ok &= all(v>0 for v in windows.values()) and sum(x>0 for x in folds)>=3
decision='P305_FIXED_COMBINATION_COST_ROBUST' if ok else 'P305_COST_SENSITIVITY_WEAKNESS'
out={'schema':'research.p305_spmo_smallvalue_cost_stress_r1','parent':'P305','claim':'Stress the unchanged P304 fixed 50/50 SPMO+IJS combination against 50/50 SPY+IJR at predeclared 10/25/50 bp endpoint turnover costs. No weight, component, window, or cadence search.','cost_bps':COSTS,'results':res,'decision_rule':'Cost robustness requires positive matched excess in 2017+, 2020+, 2022+ and >=3/5 positive folds at every cost endpoint.','decision':decision,'limitations':['same adjusted-price provider','scientific cost robustness only','no allocation/ranking/product/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p305_spmo_smallvalue_cost_stress_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
