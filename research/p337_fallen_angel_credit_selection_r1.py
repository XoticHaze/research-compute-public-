from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf

SYMS=['ANGL','HYG','SPY']; START='2012-01-01'; END='2026-09-10'; COST_BPS=10
raw=yf.download(SYMS,start=START,end=END,auto_adjust=True,progress=False,threads=False)
px=(raw['Close'] if isinstance(raw.columns,pd.MultiIndex) else raw)[SYMS].dropna().resample('ME').last(); r=px.pct_change().dropna()
q=r.ANGL.copy(); q.iloc[0]-=COST_BPS/10000

def stats(s):
 s=s.dropna(); w=(1+s).cumprod(); yrs=len(s)/12; sd=s.std(); return {'months':int(len(s)),'cagr':float(w.iloc[-1]**(1/yrs)-1),'sharpe':float(s.mean()/sd*math.sqrt(12)) if sd>0 else 0.0,'max_drawdown':float((w/w.cummax()-1).min())}
res={}
for name,start in {'2013_plus':'2013-01-01','2016_plus':'2016-01-01','2020_plus':'2020-01-01','2022_plus':'2022-01-01'}.items():
 z=pd.DataFrame({'q':q,'hyg':r.HYG,'spy':r.SPY}).loc[start:].dropna(); a,b,c=stats(z.q),stats(z.hyg),stats(z.spy); res[name]={'fallen_angel':a,'high_yield_matched':b,'spy_context':c,'matched_excess_cagr':a['cagr']-b['cagr'],'spy_opportunity_gap_cagr':a['cagr']-c['cagr']}
z=pd.DataFrame({'q':q,'hyg':r.HYG}).loc['2013-01-01':].dropna(); folds=[stats(f.q)['cagr']-stats(f.hyg)['cagr'] for f in np.array_split(z,5)]
passed=all(res[k]['matched_excess_cagr']>0 for k in res) and sum(x>0 for x in folds)>=3
decision='P337_FALLEN_ANGEL_CREDIT_SELECTION_SUPPORTED' if passed else 'P337_FALLEN_ANGEL_CREDIT_SELECTION_NOT_SUPPORTED'
out={'schema':'research.p337_fallen_angel_credit_selection_r1','parent':'P337','claim':'Test a materially different credit-security-selection proxy: ANGL fallen-angel high yield versus HYG broad high-yield matched control after fixed 10bp external entry friction, with SPY opportunity context, fixed 2013+/2016+/2020+/2022+ windows and five chronology folds. No product, rating, rebalance, maturity, cost or date search.','cost_bps':COST_BPS,'results':res,'chronology_fold_matched_excess_cagr':folds,'positive_folds':sum(x>0 for x in folds),'decision_rule':'Support only if after-cost matched excess CAGR is positive in every fixed window and >=3/5 chronology folds. Failure closes this fixed fund-level fallen-angel implementation without product, rating, maturity, rebalance, cost or date rescue.','decision':decision,'limitations':['fund-level proxy rather than point-in-time bond selection reconstruction','HYG is a broad high-yield opportunity control but not duration/rating-cell matched','single adjusted-price provider','no portfolio ranking/allocation/runtime/broker/live authority'],'boundaries':{'scientific_authority':True,'portfolio_ranking':False,'allocation_authority':False,'runtime':False,'broker':False,'live_trading':False}}
Path('research/artifacts').mkdir(parents=True,exist_ok=True); Path('research/artifacts/p337_fallen_angel_credit_selection_r1.json').write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)); print(json.dumps(out,sort_keys=True))
