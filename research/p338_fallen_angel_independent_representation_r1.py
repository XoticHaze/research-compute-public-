from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
SYMS=['FALN','HYG','SPY']; START='2016-01-01'; END='2026-09-10'; COST_BPS=10
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna().resample('ME').last(); r=px.pct_change().dropna(); strat=r.FALN.copy(); strat.iloc[0]-=COST_BPS/10000

def stats(s):
 s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
res={}
for name,start in {'2017_plus':'2017-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items():
 z=pd.DataFrame({'q':strat,'hyg':r.HYG,'spy':r.SPY}).loc[start:].dropna(); a,b,c=stats(z.q),stats(z.hyg),stats(z.spy); res[name]={'fallen_angel':a,'high_yield_matched':b,'spy_context':c,'matched_excess_cagr':a['cagr']-b['cagr'],'spy_opportunity_gap_cagr':a['cagr']-c['cagr']}
z=pd.DataFrame({'q':strat,'hyg':r.HYG}).loc['2017-01-01':].dropna(); folds=[stats(f.q)['cagr']-stats(f.hyg)['cagr'] for f in np.array_split(z,5)]
passed=all(res[k]['matched_excess_cagr']>0 for k in res) and sum(x>0 for x in folds)>=3
decision='P338_FALLEN_ANGEL_INDEPENDENT_REPRESENTATION_SUPPORTED' if passed else 'P338_FALLEN_ANGEL_INDEPENDENT_REPRESENTATION_NOT_SUPPORTED'
out={'schema':'research.p338_fallen_angel_independent_representation_r1','parent':'P338','claim':'Independent representation adjudicator for P337: FALN versus unchanged HYG broad-high-yield matched control after fixed 10bp external entry friction, with SPY opportunity context across fixed 2017+/2020+/2022+ windows and five chronology folds. No product search beyond this predeclared representation and no rating, maturity, rebalance, cost or date tuning.','cost_bps':COST_BPS,'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Representation support requires positive matched excess in every fixed window and >=3/5 positive chronology folds. Failure is an independent representation failure; combined with P337 recent-window weakness it can close the nearby fund-level fallen-angel alpha claim without parameter rescue.','decision':decision,'limitations':['fund-level proxy rather than point-in-time bond-selection reconstruction','HYG not duration/rating-cell matched','shorter FALN history than ANGL','single adjusted-price provider','no portfolio ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p338_fallen_angel_independent_representation_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
